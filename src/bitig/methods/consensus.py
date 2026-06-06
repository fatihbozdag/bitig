"""Bootstrap consensus trees (Eder 2017).

Iterate MFW bands x replicates -> Burrows Delta -> Ward linkage -> extract clades. Aggregate
clade support as fraction-of-dendrograms. Emit majority-support consensus as Newick.
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

                for clade in _extract_clades(tree, subsample_ids):
                    if 2 <= len(clade) < n_docs:
                        clade_counts[frozenset(clade)] += 1
                total_dendrograms += 1

        if total_dendrograms == 0:
            raise ValueError("Consensus: no valid dendrograms produced (all bands culled out?)")

        support = {clade: count / total_dendrograms for clade, count in clade_counts.items()}
        majority = {clade: s for clade, s in support.items() if s >= self.support_threshold}
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
