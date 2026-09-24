"""The README carries both languages in one file; docs/ keeps a pair each.

The README uses a single bilingual layout (an `## English` section and an
`## 中文` section) because that is the house style. The docs/ directory keeps
separate Chinese and English files. This test keeps both honest: links
resolve, images exist, the two languages stay in sync, and the language-neutral
code blocks never drift.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
DOC_PAIRS = (
    ("docs/architecture.md", "docs/architecture.en.md"),
    ("docs/product-contract.md", "docs/product-contract.en.md"),
    ("docs/roadmap.md", "docs/roadmap.en.md"),
)
LINK = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
FENCE = re.compile(r"```[a-z]*\n(.*?)```", re.S)

README_EN = "## English"
README_ZH = "## 中文"
ALL_DOCS = (README, *(ROOT / zh for zh, _ in DOC_PAIRS), *(ROOT / en for _, en in DOC_PAIRS))


def readme_sections() -> tuple[str, str]:
    """Split the bilingual README into its English and Chinese halves."""
    text = README.read_text(encoding="utf-8")
    return text[text.index(README_EN): text.index(README_ZH)], text[text.index(README_ZH):]


class ReadmeTests(unittest.TestCase):
    def test_readme_carries_both_languages(self) -> None:
        english, chinese = readme_sections()
        self.assertGreater(len(english), 500, "English section looks empty")
        self.assertGreater(len(chinese), 500, "Chinese section looks empty")
        self.assertRegex(chinese, r"[\u4e00-\u9fff]")

    def test_readme_opens_with_a_language_switch(self) -> None:
        head = README.read_text(encoding="utf-8")[:600]
        self.assertIn('<div align="center">', head)
        self.assertIn("[English](#english)", head)
        self.assertIn("[中文](#中文)", head)

    def test_readme_sections_have_matching_structure(self) -> None:
        english, chinese = readme_sections()
        self.assertEqual(
            len(re.findall(r"^#+ ", english, re.M)),
            len(re.findall(r"^#+ ", chinese, re.M)),
            "heading count drifted between the two languages",
        )
        self.assertEqual(
            len(FENCE.findall(english)),
            len(FENCE.findall(chinese)),
            "code block count drifted between the two languages",
        )

    def test_readme_code_blocks_are_identical_across_languages(self) -> None:
        """Commands, JSON and Python are language neutral."""
        english, chinese = readme_sections()
        for index, (a, b) in enumerate(zip(FENCE.findall(english), FENCE.findall(chinese)), 1):
            with self.subTest(block=index):
                self.assertEqual(a, b, f"code block {index} drifted between languages")

    def test_readme_code_blocks_use_real_flags(self) -> None:
        """A flag invented for the README would be worse than no mention of it."""
        english, _ = readme_sections()
        text = "\n".join(FENCE.findall(english))
        self.assertIn("mcp-ward snapshot", text)
        self.assertIn("mcp-ward check", text)
        for flag in ("--profile", "--format", "--report-dir", "--lang", "--baseline-ref"):
            with self.subTest(flag=flag):
                self.assertIn(flag, text)


class ImageTests(unittest.TestCase):
    def test_every_referenced_image_exists(self) -> None:
        for doc in ALL_DOCS:
            text = doc.read_text(encoding="utf-8")
            for _alt, target in IMAGE.findall(text):
                if target.startswith(("http://", "https://")):
                    continue
                with self.subTest(doc=doc.name, image=target):
                    self.assertTrue(
                        (doc.parent / target).resolve().exists(),
                        f"{doc.name}: missing image {target}",
                    )

    def test_screenshots_are_not_empty(self) -> None:
        for png in (ROOT / "screenshots").glob("*.png"):
            with self.subTest(image=png.name):
                self.assertGreater(png.stat().st_size, 5000, f"{png.name} looks blank")


class DocPairTests(unittest.TestCase):
    def test_every_chinese_doc_has_an_english_pair(self) -> None:
        for chinese, english in DOC_PAIRS:
            with self.subTest(doc=chinese):
                self.assertTrue((ROOT / chinese).exists(), f"missing {chinese}")
                self.assertTrue((ROOT / english).exists(), f"missing {english}")

    def test_every_relative_link_resolves(self) -> None:
        for path in ALL_DOCS:
            text = path.read_text(encoding="utf-8")
            for _label, target in LINK.findall(text):
                if target.startswith(("http://", "https://", "#")):
                    continue
                with self.subTest(doc=path.name, link=target):
                    self.assertTrue(
                        (path.parent / target).resolve().exists(),
                        f"{path.name}: broken link -> {target}",
                    )

    def test_internal_anchors_resolve(self) -> None:
        """`#english` and `#中文` must match a real heading."""
        text = README.read_text(encoding="utf-8")
        headings = {
            re.sub(r"[^\w\u4e00-\u9fff-]", "", line.lstrip("#").strip()).lower()
            for line in text.splitlines() if line.startswith("#")
        }
        for _label, target in LINK.findall(text):
            if not target.startswith("#"):
                continue
            anchor = re.sub(r"[^\w\u4e00-\u9fff-]", "", target[1:]).lower()
            with self.subTest(anchor=anchor):
                self.assertIn(anchor, headings, f"no heading matches {target}")

    def test_translated_pairs_keep_the_same_structure(self) -> None:
        for chinese, english in DOC_PAIRS:
            with self.subTest(doc=chinese):
                zh = (ROOT / chinese).read_text(encoding="utf-8")
                en = (ROOT / english).read_text(encoding="utf-8")
                self.assertEqual(
                    len(re.findall(r"^#+ ", zh, re.M)),
                    len(re.findall(r"^#+ ", en, re.M)),
                    f"{chinese}: heading count drifted from {english}",
                )
                self.assertEqual(
                    len(FENCE.findall(zh)),
                    len(FENCE.findall(en)),
                    f"{chinese}: code block count drifted from {english}",
                )

    def test_doc_code_blocks_are_identical_across_translations(self) -> None:
        for chinese, english in DOC_PAIRS:
            zh = FENCE.findall((ROOT / chinese).read_text(encoding="utf-8"))
            en = FENCE.findall((ROOT / english).read_text(encoding="utf-8"))
            for index, (a, b) in enumerate(zip(zh, en), 1):
                with self.subTest(doc=chinese, block=index):
                    self.assertEqual(a, b, f"{chinese}: code block {index} drifted")

    def test_no_standalone_english_readme_remains(self) -> None:
        """The English half now lives inside README.md, not a second file."""
        self.assertFalse((ROOT / "README.en.md").exists())
        self.assertFalse((ROOT / "README.zh-CN.md").exists())

    def test_default_readme_is_the_bilingual_one(self) -> None:
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('readme = "README.md"', pyproject)


if __name__ == "__main__":
    unittest.main()
