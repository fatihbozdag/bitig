"""Bootstrap consensus trees (Eder 2017).

Iterate MFW bands x replicates -> Burrows Delta -> Ward linkage -> extract clades. Each
replicate subsamples documents, so a tree only shows the clades of the documents it
contains. A clade's support is therefore the fraction of trees **containing all of its
members** in which it appears as a clade (audit 2026-09-26 P2: dividing by every tree,
and counting the whole-subsample root as a clade, misstated support). Clades with support
strictly greater than ``support_threshold`` (majority rule: > 0.5) form the consensus,
emitted as Newick.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from scipy.cluster.hierarchy import linkage, to_tree

from bitig.corpus import Corpus
from bitig.features import MFWExtractor
from bitig.plumbing.seeds import derive_rng
from bitig.result import Result


class BootstrapConsensus:
    def __init__(
        self,
        *,
        mfw_bands: list[int],
        replicates: int = 100,
        subsample: float = 0.8,
        support_threshold: float = 0.5,
        seed: int = 42,
    ) -> None:
        self.mfw_bands = list(mfw_bands)
        self.replicates = replicates
        self.subsample = subsample
        self.support_threshold = support_threshold
        if not 0.0 < subsample <= 1.0:
            raise ValueError(f"subsample must be in (0, 1], got {subsample}")
        if not 0.0 <= support_threshold < 1.0:
            raise ValueError(f"support_threshold must be in [0, 1), got {support_threshold}")
        self.seed = seed

    def fit_transform(self, corpus: Corpus) -> Result:
        doc_ids = [d.id for d in corpus.documents]
        n_docs = len(doc_ids)
        if n_docs < 2:
            raise ValueError(
                f"Bootstrap consensus needs at least 2 documents, got {n_docs}. "
                "A consensus tree is undefined for a single document."
            )
        rng = derive_rng(self.seed, "consensus")

        clade_counts: Counter[frozenset[str]] = Counter()
        tree_leaf_sets: list[frozenset[str]] = []
        total_dendrograms = 0

        for band in self.mfw_bands:
            for _ in range(self.replicates):
                idx = rng.choice(n_docs, size=max(2, int(n_docs * self.subsample)), replace=False)
                subsample_corpus = Corpus(documents=[corpus.documents[int(i)] for i in idx])
                subsample_ids = [d.id for d in subsample_corpus.documents]

                mfw = MFWExtractor(n=band, min_df=2, scale="zscore", lowercase=True)
                fm = mfw.fit_transform(subsample_corpus)
                if fm.X.shape[1] == 0:
                    continue  # No MFW survived culling; skip this replicate.

                Z = linkage(fm.X, method="ward")  # noqa: N806
                tree = to_tree(Z, rd=False)  # type: ignore[arg-type]

                leaf_set = frozenset(subsample_ids)
                for clade in _extract_clades(tree, subsample_ids):
                    # The root (all leaves of this tree) carries no information.
                    if 2 <= len(clade) < len(leaf_set):
                        clade_counts[frozenset(clade)] += 1
                tree_leaf_sets.append(leaf_set)
                total_dendrograms += 1

        if total_dendrograms == 0:
            raise ValueError("Consensus: no valid dendrograms produced (all bands culled out?)")

        support: dict[frozenset[str], float] = {}
        for members, count in clade_counts.items():
            eligible = sum(1 for leaves in tree_leaf_sets if members <= leaves)
            support[members] = count / eligible
        majority = {clade: s for clade, s in support.items() if s > self.support_threshold}
        newick = _build_newick(doc_ids, majority)

        return Result(
            method_name="bootstrap_consensus",
            params={
                "mfw_bands": self.mfw_bands,
                "replicates": self.replicates,
                "subsample": self.subsample,
                "support_threshold": self.support_threshold,
                "seed": self.seed,
            },
            values={
                "newick": newick,
                "support": {",".join(sorted(c)): s for c, s in support.items()},
                "total_dendrograms": total_dendrograms,
                "document_ids": doc_ids,
            },
        )


def _extract_clades(node: Any, leaf_ids: list[str]) -> list[list[str]]:
    """Return every internal node's leaf-ID set."""
    if node.is_leaf():
        return []
    left = _leaves_of(node.left, leaf_ids)
    right = _leaves_of(node.right, leaf_ids)
    here = left + right
    out = [here]
    out.extend(_extract_clades(node.left, leaf_ids))
    out.extend(_extract_clades(node.right, leaf_ids))
    return out


def _leaves_of(node: Any, leaf_ids: list[str]) -> list[str]:
    if node.is_leaf():
        return [leaf_ids[node.id]]
    return _leaves_of(node.left, leaf_ids) + _leaves_of(node.right, leaf_ids)


def _build_newick(leaves: list[str], clades_with_support: dict[frozenset[str], float]) -> str:
    """Build a Newick string where internal branches are annotated with support values.

    Algorithm: compatibility via greedy nesting. Sort clades by size (largest first) so parents
    encapsulate children. A minority-supported set of "missing" internal relationships becomes
    a flat polytomy at the root.
    """
    ordered = sorted(clades_with_support.items(), key=lambda kv: (-len(kv[0]), sorted(kv[0])))
    clade_children: dict[frozenset[str], list[frozenset[str] | str]] = defaultdict(list)

    # Build containment tree: each clade's direct children are the largest sub-clades it contains
    # that haven't been parented elsewhere.
    remaining_leaves = set(leaves)
    clade_list = [c for c, _ in ordered]
    for c in clade_list:
        clade_children[c] = []
    placed: set[frozenset[str]] = set()
    for parent in clade_list:
        for child in clade_list:
            if child is parent or child in placed:
                continue
            if child < parent and not any(
                child < other < parent for other in clade_list if other != parent and other != child
            ):
                clade_children[parent].append(child)
                placed.add(child)

    def render(clade: frozenset[str]) -> str:
        child_clades = clade_children.get(clade, [])
        child_leaves = clade - frozenset().union(*child_clades) if child_clades else clade
        parts = [render(c) for c in child_clades] + sorted(child_leaves)  # type: ignore[arg-type]
        return "(" + ",".join(parts) + f"){clades_with_support[clade]:.2f}"

    top = [c for c in clade_list if c not in placed]
    if not top:
        # All leaves flat at root.
        return "(" + ",".join(sorted(remaining_leaves)) + ");"

    covered = frozenset().union(*top)
    stray = remaining_leaves - covered
    rendered_tops = [render(c) for c in top] + sorted(stray)
    return "(" + ",".join(rendered_tops) + ");"
