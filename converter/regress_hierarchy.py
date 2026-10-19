"""Hierarchy contract for the emitted structured content.

Every earlier gate looked at ONE level at a time -- "is an <li> inside a list",
"does the CSS carry the hanging indent" -- so a whole class of layout bug went
through 14/14 green: a node could be correct on its own and still sit one level
too deep relative to its siblings. Three real ones were found by measuring the
rendered left edge in Chrome:

  * div.ld-gramexa / div.ld-colloexa were members of EXAMPLE_ITEM_CLASSES, so
    the head was wrapped in a classless <li>, carried the example dash and the
    example indent, and then indented its own <ul> a second time. The examples
    under a head sat one full level below the examples next to it.
  * div.ld-subsense was a member of SENSE_ITEM_CLASSES, so every subsense was
    wrapped in an extra <ol class="ld-senselist"> + <li>. A host without our
    stylesheet numbered those items "1. 2. 3." on top of the a)/b) labels.
  * the same node therefore appeared at two different columns depending on the
    path that produced it.

Three invariants, all checkable without a browser:

  1. No <li> is a bare wrapper around a block that carries its own list class
     (ld-subsense / ld-gramexa / ld-colloexa). Such an <li> has no class of its
     own, so every class-scoped rule misses it, and its padding stacks.
  2. Those three classes are never emitted as <li> themselves.
  3. An <ol class="ld-senselist"> never directly contains a non-sense item:
     subsenses are blocks inside the parent sense, not numbered list members.

Usage:  python regress_hierarchy.py <package.zip> [...]
Exit code 0 = all invariants hold.
"""
import json
import re
import sys
import zipfile

WRAPPER_CLASSES = {"ld-subsense", "ld-gramexa", "ld-colloexa"}
SENSE_ITEM = {"ld-sense", "ld-sense-cross", "ld-sense-merge"}


def rows(z, name):
    text = z.read(name).decode("utf8")
    data = json.loads(text)
    if isinstance(data, list) and data and isinstance(data[0], list):
        return data
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def kids(node):
    content = node.get("content")
    if content is None:
        return []
    return content if isinstance(content, list) else [content]


def cls(node):
    return (node.get("data") or {}).get("class") or ""


def check(zip_path):
    stats = {"entries": 0, "li": 0, "wrapper_li": 0, "class_as_li": 0,
             "non_sense_in_senselist": 0, "nested_exlist": 0}
    problems = []

    z = zipfile.ZipFile(zip_path)
    for name in sorted(n for n in z.namelist()
                       if re.fullmatch(r"term_bank_\d+\.json", n)):
        for row in rows(z, name):
            stats["entries"] += 1
            word = row[0]

            def walk(node, in_exlist=False):
                if isinstance(node, list):
                    for x in node:
                        walk(x, in_exlist)
                    return
                if not isinstance(node, dict):
                    return
                tag = node.get("tag")
                toks = set(cls(node).split())
                if tag == "li":
                    stats["li"] += 1
                    inner = [k for k in kids(node) if isinstance(k, dict)]
                    if not toks and inner and set(cls(inner[0]).split()) & WRAPPER_CLASSES:
                        stats["wrapper_li"] += 1
                        if len(problems) < 20:
                            problems.append(("wrapper <li>", word, cls(inner[0])))
                if toks & WRAPPER_CLASSES and tag == "li":
                    stats["class_as_li"] += 1
                    if len(problems) < 20:
                        problems.append(("list class on <li>", word,
                                         sorted(toks & WRAPPER_CLASSES)[0]))
                if tag == "ol" and "ld-senselist" in toks:
                    for k in kids(node):
                        if not isinstance(k, dict) or k.get("tag") != "li":
                            if isinstance(k, str) and not k.strip():
                                continue
                            stats["non_sense_in_senselist"] += 1
                            if len(problems) < 20:
                                problems.append(("non-<li> in senselist", word,
                                                 k.get("tag") if isinstance(k, dict) else "text"))
                            continue
                        kt = set(cls(k).split())
                        if not (kt & SENSE_ITEM):
                            stats["non_sense_in_senselist"] += 1
                            if len(problems) < 20:
                                problems.append(("non-sense item in senselist", word,
                                                 cls(k) or "<no class>"))
                # An example list nested anywhere inside another example list is
                # the signature of a group head rendered as a list member: the
                # head became an <li> and its own examples became a second <ul>
                # one level deeper.
                if tag == "ul" and "ld-exlist" in toks and in_exlist:
                    stats["nested_exlist"] += 1
                    if len(problems) < 20:
                        problems.append(("nested exlist", word, "inside an example item"))
                next_in_exlist = in_exlist or (tag == "ul" and "ld-exlist" in toks)
                for k in kids(node):
                    walk(k, next_in_exlist)

            walk(row[5])

    return stats, problems


def main(argv):
    if len(argv) < 2:
        print("usage: regress_hierarchy.py <package.zip> [...]")
        return 2
    failed = False
    for path in argv[1:]:
        stats, problems = check(path)
        print(f"\n== {path}")
        print(f"   entries={stats['entries']:,} li={stats['li']:,} "
              f"wrapper_li={stats['wrapper_li']:,} "
              f"class_as_li={stats['class_as_li']:,} "
              f"non_sense_in_senselist={stats['non_sense_in_senselist']:,} "
              f"nested_exlist={stats['nested_exlist']:,}")
        bad = (stats["wrapper_li"] or stats["class_as_li"]
               or stats["non_sense_in_senselist"] or stats["nested_exlist"])
        if bad:
            failed = True
            print("   FAIL -- offenders (first 20):")
            for p in problems:
                print("     ", p)
        else:
            print("   PASS -- no wrapper <li>, no misplaced list class, "
                  "no subsense in a senselist")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
