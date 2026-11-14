"""Sequence windows for single-nucleotide variants. Standard library only.

Method: the BRCA1 zero-shot notebook in ArcInstitute/evo2 (8,192-bp window on the
plus strand, 4,096 bases upstream of the variant, the variant, 4,095 downstream).
The minus-strand option returns the reverse complement of the same window.
Research use only; not for clinical decisions.
"""
import gzip

_COMPLEMENT = str.maketrans("ACGTacgt", "TGCAtgca")


def reverse_complement(seq):
    return seq.translate(_COMPLEMENT)[::-1]


def read_first_fasta_record(path):
    """Return (header, sequence) of the first record of a plain or gzip FASTA."""
    opener = gzip.open if str(path).endswith(".gz") else open
    header, parts = None, []
    with opener(path, "rt") as handle:
        for line in handle:
            if line.startswith(">"):
                if header is not None:
                    break
                header = line[1:].strip()
                continue
            parts.append(line.strip())
    return header, "".join(parts)


def build_windows(seq, pos, ref, alt, window=8192, strand="+"):
    """Build the reference and alternate windows for one SNV.

    seq    plus-strand chromosome sequence
    pos    1-based position on the plus strand
    ref    plus-strand reference base, alt: plus-strand alternate base
    strand '+' gives the plus-strand window; '-' gives its reverse complement

    Returns a dict with ref_seq, var_seq, start (0-based, inclusive), end (0-based,
    exclusive), index (0-based index of the variant base inside the returned
    window) and base_at_index (the alternate base as written on that strand).
    """
    ref, alt = ref.upper(), alt.upper()
    if len(ref) != 1 or len(alt) != 1 or ref == alt or ref not in "ACGT" or alt not in "ACGT":
        raise ValueError("not a single-nucleotide substitution")
    if strand not in ("+", "-"):
        raise ValueError("strand must be '+' or '-'")
    p = pos - 1
    if p < 0 or p >= len(seq):
        raise ValueError("position outside the sequence")
    start = max(0, p - window // 2)
    end = min(len(seq), p + window // 2)
    ref_seq = seq[start:end].upper()
    k = p - start
    if ref_seq[k] != ref:
        raise ValueError(f"reference mismatch at {pos}: sequence has {ref_seq[k]}, table has {ref}")
    if set(ref_seq) - set("ACGT"):
        raise ValueError("window contains non-ACGT characters")
    var_seq = ref_seq[:k] + alt + ref_seq[k + 1:]
    base = alt
    if strand == "-":
        ref_seq = reverse_complement(ref_seq)
        var_seq = reverse_complement(var_seq)
        k = len(ref_seq) - 1 - k
        base = reverse_complement(alt)
    assert len(var_seq) == len(ref_seq) and var_seq[k] == base
    return {"ref_seq": ref_seq, "var_seq": var_seq, "start": start, "end": end,
            "index": k, "base_at_index": base}
