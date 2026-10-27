import hashlib

from ml.preprocessing.file_integrity import sha256_file


def test_csv_line_endings_are_normalized_even_when_crlf_crosses_a_read_chunk(tmp_path):
    content = b"a" * (1024 * 1024 - 1) + b"\r\nb\r\n"
    csv_path = tmp_path / "dataset.csv"
    csv_path.write_bytes(content)

    assert sha256_file(csv_path) == hashlib.sha256(content).hexdigest()
    assert sha256_file(csv_path, normalize_csv_line_endings=True) == hashlib.sha256(
        content.replace(b"\r\n", b"\n")
    ).hexdigest()


def test_non_csv_hashes_remain_byte_exact(tmp_path):
    content = b"binary\r\ncontent"
    source_path = tmp_path / "source.bin"
    source_path.write_bytes(content)

    assert sha256_file(source_path, normalize_csv_line_endings=True) == hashlib.sha256(content).hexdigest()
