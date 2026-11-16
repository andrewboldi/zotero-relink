"""zotero-relink keeps Zotero's linked files linked when they are moved or renamed outside Zotero."""
import json
import os

from zotero_relink.fixer import fix


def remembered(env):
    return json.loads(env.state.read_text())["files"]


# ---- the first run only remembers ----

def test_the_first_run_remembers_every_file_and_changes_nothing(env):
    env.link("AAAA0001", env.file("papers/a.pdf"))
    report = env.fix()
    assert report.checked == 1 and not report.relinked and not report.missing
    assert env.server.writes == []
    assert set(remembered(env)) == {"AAAA0001"}


def test_a_link_whose_file_was_already_missing_is_reported_not_searched(env):
    env.link("AAAA0001", env.home / "never-here.pdf")
    report = env.fix()
    assert [(m.key, m.reason) for m in report.missing] == [("AAAA0001", "missing before zotero-relink first saw it")]
    assert env.server.writes == []


# ---- moves and renames are followed ----

def test_a_renamed_file_is_relinked(env):
    f = env.file("papers/a.pdf")
    env.link("AAAA0001", f)
    env.fix()
    new = f.with_name("Smith - 2020 - A Better Name.pdf")
    f.rename(new)
    report = env.fix()
    assert env.server.path("AAAA0001") == str(new)
    assert [(r.key, r.old, r.new, r.how) for r in report.relinked] == [("AAAA0001", str(f), str(new), "inode")]


def test_an_attachment_titled_after_its_old_file_name_takes_the_new_name(env):
    f = env.file("papers/a.pdf")
    env.link("AAAA0001", f)
    env.fix()
    f.rename(f.with_name("b.pdf"))
    env.fix()
    assert env.server.title("AAAA0001") == "b.pdf"


def test_an_attachment_with_a_title_of_its_own_keeps_it(env):
    f = env.file("papers/a.pdf")
    env.link("AAAA0001", f, title="Full Text PDF")
    env.fix()
    f.rename(f.with_name("b.pdf"))
    env.fix()
    assert env.server.title("AAAA0001") == "Full Text PDF"


def test_a_file_moved_to_another_folder_is_relinked(env):
    f = env.file("Downloads/a.pdf")
    env.link("AAAA0001", f)
    env.fix()
    dest = env.home / "library" / "Chemistry" / "a.pdf"
    dest.parent.mkdir(parents=True)
    f.rename(dest)
    env.fix()
    assert env.server.path("AAAA0001") == str(dest)


def test_renaming_a_folder_relinks_every_file_in_it(env):
    one, two = env.file("course/hw/1.pdf", b"one"), env.file("course/hw/2.pdf", b"two")
    env.link("AAAA0001", one)
    env.link("AAAA0002", two)
    env.fix()
    (env.home / "course/hw").rename(env.home / "course/homework")
    report = env.fix()
    assert env.server.path("AAAA0001") == str(env.home / "course/homework/1.pdf")
    assert env.server.path("AAAA0002") == str(env.home / "course/homework/2.pdf")
    assert len(report.relinked) == 2


def test_a_file_rewritten_somewhere_else_is_found_by_its_content(env):
    f = env.file("a.pdf", b"the same bytes")
    env.link("AAAA0001", f)
    env.fix()
    copy = env.file("elsewhere/renamed.pdf", b"the same bytes")   # a new inode: a copy, git, another disk
    f.unlink()
    report = env.fix()
    assert env.server.path("AAAA0001") == str(copy)
    assert report.relinked[0].how == "content"


def test_a_file_moved_twice_before_zotero_syncs_is_followed(env):
    f = env.file("a.pdf")
    env.link("AAAA0001", f)
    env.fix()
    b = f.with_name("b.pdf")
    f.rename(b)
    env.fix()
    c = f.with_name("c.pdf")
    b.rename(c)
    env.fix()
    assert env.server.path("AAAA0001") == str(c)


def test_a_file_edited_in_place_is_not_a_move(env):
    f = env.file("a.pdf", b"v1")
    env.link("AAAA0001", f)
    env.fix()
    f.write_bytes(b"version two")
    report = env.fix()
    assert not report.relinked and not report.missing and env.server.writes == []


def test_a_file_edited_and_later_copied_away_is_still_found(env):
    f = env.file("a.pdf", b"v1")
    env.link("AAAA0001", f)
    env.fix()
    f.write_bytes(b"version two")
    env.fix()                                   # zotero-relink notices the new content
    copy = env.file("b/a.pdf", b"version two")
    f.unlink()
    env.fix()
    assert env.server.path("AAAA0001") == str(copy)


# ---- no guessing ----

def test_of_identical_copies_the_one_with_the_old_file_name_wins(env):
    f = env.file("a.pdf", b"same")
    env.link("AAAA0001", f)
    env.fix()
    env.file("x/other.pdf", b"same")
    keep = env.file("y/a.pdf", b"same")
    f.unlink()
    env.fix()
    assert env.server.path("AAAA0001") == str(keep)


def test_identical_copies_it_cannot_tell_apart_are_reported_not_guessed(env):
    f = env.file("a.pdf", b"same")
    env.link("AAAA0001", f)
    env.fix()
    env.file("x/a.pdf", b"same")
    env.file("y/a.pdf", b"same")
    f.unlink()
    report = env.fix()
    assert env.server.writes == []
    assert [(m.key, m.reason) for m in report.missing] == [("AAAA0001", "2 identical copies")]


def test_a_deleted_file_is_reported_and_its_link_left_alone(env):
    f = env.file("a.pdf")
    env.link("AAAA0001", f)
    env.fix()
    f.unlink()
    report = env.fix()
    assert env.server.writes == [] and [m.reason for m in report.missing] == ["not found"]


def test_a_file_in_the_trash_is_reported_as_trashed_and_not_linked_there(env):
    f = env.file("a.pdf")
    env.link("AAAA0001", f)
    env.fix()
    env.trash.mkdir(parents=True)
    f.rename(env.trash / "a.pdf")
    report = env.fix()
    assert env.server.writes == [] and [m.reason for m in report.missing] == ["in the trash"]


def test_hidden_folders_are_not_searched(env):
    f = env.file("a.pdf")
    env.link("AAAA0001", f)
    env.fix()
    hidden = env.home / ".cache" / "a.pdf"
    hidden.parent.mkdir()
    f.rename(hidden)
    report = env.fix()
    assert env.server.writes == [] and [m.reason for m in report.missing] == ["not found"]


def test_skipped_folders_are_not_searched(env):
    f = env.file("a.pdf", b"paper")
    env.link("AAAA0001", f)
    env.fix()
    env.file("Zotero/storage/ABCD1234/a.pdf", b"paper")   # Zotero's own copy must never become the link
    f.unlink()
    report = env.fix(skip=[env.home / "Zotero"])
    assert env.server.writes == [] and [m.reason for m in report.missing] == ["not found"]


def test_an_unrelated_file_that_reuses_the_inode_is_not_taken(env):
    f = env.file("a.pdf", b"original paper")
    env.link("AAAA0001", f)
    env.fix()
    other = env.file("other.pdf", b"something else entirely")
    state = json.loads(env.state.read_text())
    state["files"]["AAAA0001"]["ino"] = other.stat().st_ino      # as if the filesystem reused the number
    env.state.write_text(json.dumps(state))
    f.unlink()
    report = env.fix()
    assert env.server.writes == [] and [m.reason for m in report.missing] == ["not found"]


# ---- searching costs: a deleted file must not mean a full search every run ----

def test_a_file_lost_for_a_while_is_searched_for_again_only_later(env):
    f = env.file("papers/sub/a.pdf")
    env.link("AAAA0001", f)
    env.fix(now=1000)
    outside = env.home.parent / "outside.pdf"
    f.rename(outside)                                   # gone from home
    assert [m.reason for m in env.fix(now=2000).missing] == ["not found"]
    back = env.home / "other" / "a.pdf"
    back.parent.mkdir()
    outside.rename(back)                                # turns up far from where it was
    assert [m.reason for m in env.fix(now=2100).missing] == ["not found"]   # no full search yet
    env.fix(now=2000 + 3600 + 1)
    assert env.server.path("AAAA0001") == str(back)


def test_the_wait_between_full_searches_doubles(env):
    f = env.file("papers/sub/a.pdf")
    env.link("AAAA0001", f)
    env.fix(now=0)
    f.unlink()
    env.fix(now=10)                                     # full search, then wait 1 h
    env.fix(now=10 + 3601)                              # full search, then wait 2 h
    moved = env.file("elsewhere/a.pdf", b"%PDF-1.4 some paper")   # same content, far away
    env.fix(now=10 + 3601 + 3601)                       # within the 2 h wait: not searched
    assert env.server.path("AAAA0001") == str(f)
    env.fix(now=10 + 3601 + 7201)
    assert env.server.path("AAAA0001") == str(moved)


def test_a_lost_file_that_turns_up_near_where_it_was_is_found_at_once(env):
    f = env.file("papers/sub/a.pdf")
    env.link("AAAA0001", f)
    env.fix(now=1000)
    outside = env.home.parent / "outside.pdf"
    f.rename(outside)
    env.fix(now=2000)                                   # not found; full searches now wait
    near = env.home / "papers" / "sub" / "renamed.pdf"
    outside.rename(near)
    env.fix(now=2100)
    assert env.server.path("AAAA0001") == str(near)


def test_a_rename_in_a_deep_folder_is_found_without_searching_elsewhere(env, monkeypatch):
    f = env.file("a/b/c/paper.pdf")
    env.link("AAAA0001", f)
    env.fix()
    env.file("big/elsewhere/x.pdf")
    import zotero_relink.finder as finder
    seen = []
    real_walk = finder.walk
    monkeypatch.setattr(finder, "walk", lambda roots, *a, **k: (seen.extend(map(str, roots)), real_walk(roots, *a, **k))[1])
    f.rename(f.with_name("renamed.pdf"))
    env.fix()
    assert env.server.path("AAAA0001") == str(f.with_name("renamed.pdf"))
    assert seen == [str(env.home / "a/b/c")]


# ---- Zotero's side ----

def test_a_fix_is_not_sent_again_while_zotero_desktop_catches_up(env):
    f = env.file("a.pdf")
    env.link("AAAA0001", f)
    env.fix()
    new = f.with_name("b.pdf")
    f.rename(new)
    env.fix()                              # fixed on the server; the local database still has the old path
    sent = len(env.server.writes)
    report = env.fix()
    assert len(env.server.writes) == sent and report.waiting == ["AAAA0001"] and not report.missing
    env.db.set_path("AAAA0001", new)       # Zotero desktop syncs
    report = env.fix()
    assert report.waiting == [] and not report.missing and not report.relinked


def test_a_link_changed_in_zotero_meanwhile_is_left_alone(env):
    f = env.file("a.pdf")
    env.link("AAAA0001", f)
    env.fix()
    f.rename(f.with_name("b.pdf"))
    env.server.items["AAAA0001"]["data"]["path"] = "/somewhere/else.pdf"   # relinked by hand in Zotero
    report = env.fix()
    assert env.server.path("AAAA0001") == "/somewhere/else.pdf"
    assert [m.reason for m in report.missing] == ["changed in Zotero since"]


def test_other_edits_made_meanwhile_are_kept(env):
    f = env.file("a.pdf")
    env.link("AAAA0001", f)
    env.fix()
    new = f.with_name("b.pdf")
    f.rename(new)
    env.server.items["AAAA0001"]["data"]["tags"] = [{"tag": "to read"}]
    env.server.bump("AAAA0001")
    env.fix()
    assert env.server.path("AAAA0001") == str(new)
    assert env.server.items["AAAA0001"]["data"]["tags"] == [{"tag": "to read"}]


def test_a_write_that_loses_a_race_is_retried_once(env):
    f = env.file("a.pdf")
    env.link("AAAA0001", f)
    env.fix()
    new = f.with_name("b.pdf")
    f.rename(new)
    env.server.refuse["AAAA0001"] = [(412, "Item has been modified since specified version")]
    report = env.fix()
    assert env.server.path("AAAA0001") == str(new) and not report.failed


def test_a_write_the_server_keeps_refusing_is_reported(env):
    f = env.file("a.pdf")
    env.link("AAAA0001", f)
    env.fix()
    f.rename(f.with_name("b.pdf"))
    env.server.refuse["AAAA0001"] = [(403, "Write access denied"), (403, "Write access denied")]
    report = env.fix()
    assert [(x.key, x.code) for x in report.failed] == [("AAAA0001", 403)]
    assert env.server.path("AAAA0001") == str(f)


def test_items_in_zoteros_trash_are_ignored(env):
    f = env.file("a.pdf")
    env.db.attachment("AAAA0001", f, "a.pdf", deleted=True)
    parent = env.db.parent("PPPP0001", deleted=True)
    env.db.attachment("AAAA0002", env.file("b.pdf", b"b"), "b.pdf", parent=parent)
    report = env.fix()
    assert report.checked == 0


def test_only_linked_files_in_the_personal_library_are_handled(env):
    env.db.attachment("AAAA0001", "storage:a.pdf", "a.pdf", link_mode=0)        # stored by Zotero itself
    env.db.attachment("AAAA0002", env.file("g.pdf"), "g.pdf", library=2)        # a group library
    report = env.fix()
    assert report.checked == 0


def test_paths_relative_to_the_base_directory_stay_relative(env):
    base = env.home / "Papers"
    f = env.file("Papers/a.pdf")
    env.db.attachment("AAAA0001", "attachments:a.pdf", "a.pdf")
    env.server.add("AAAA0001", "attachments:a.pdf", "a.pdf")
    env.fix(base_dir=base)
    (base / "sub").mkdir()
    f.rename(base / "sub" / "a.pdf")
    env.fix(base_dir=base)
    assert env.server.path("AAAA0001") == "attachments:sub/a.pdf"


def test_the_zotero_database_is_never_written(env):
    f = env.file("a.pdf")
    env.link("AAAA0001", f)
    env.fix()
    f.rename(f.with_name("b.pdf"))
    before = env.db.path.read_bytes()
    env.fix()
    assert env.db.path.read_bytes() == before


# ---- dry run ----

def test_a_dry_run_reports_what_it_would_do_and_changes_nothing(env):
    f = env.file("a.pdf")
    env.link("AAAA0001", f)
    env.fix()
    new = f.with_name("b.pdf")
    f.rename(new)
    state_before = env.state.read_bytes()
    report = env.fix(dry_run=True)
    assert env.server.writes == [] and env.state.read_bytes() == state_before
    assert report.dry_run and [(r.key, r.new) for r in report.relinked] == [("AAAA0001", str(new))]


def test_a_dry_run_needs_no_api(env):
    f = env.file("a.pdf")
    env.link("AAAA0001", f)
    env.fix()
    f.rename(f.with_name("b.pdf"))
    report = fix(env.db.path, env.state, roots=[env.home], api=None, dry_run=True, trash_dirs=[env.trash])
    assert len(report.relinked) == 1


# ---- external drives ----

def test_a_file_moved_onto_an_external_drive_is_followed(env, tmp_path):
    drive = tmp_path / "drive"
    drive.mkdir()
    f = env.file("Papers/a.pdf", b"a big pdf")
    env.link("AAAA0001", f)
    env.fix(roots=[env.home, drive])
    dest = drive / "Papers" / "a.pdf"
    dest.parent.mkdir()
    dest.write_bytes(f.read_bytes())    # moving between disks is a copy and a delete
    f.unlink()
    env.fix(roots=[env.home, drive])
    assert env.server.path("AAAA0001") == str(dest)


def test_a_file_on_an_unplugged_drive_is_left_alone(env, tmp_path):
    drive = tmp_path / "drive"
    drive.mkdir()
    f = drive / "a.pdf"
    f.write_bytes(b"lives on the drive")
    env.link("AAAA0001", f)
    env.file("Backup/a.pdf", b"lives on the drive")      # an identical copy at home
    env.fix(roots=[env.home, drive])
    drive.rename(tmp_path / "unplugged")                  # the drive goes away
    report = env.fix(roots=[env.home], offline=lambda p: p.startswith(str(drive) + "/"))
    assert env.server.writes == []
    assert [m.reason for m in report.missing] == ["its drive isn't connected"]


def test_an_inode_match_also_needs_the_same_modification_time(env):
    # FAT and exFAT drives make inode numbers up, so a number can come back on another file.
    f = env.file("a.pdf", b"12345")
    env.link("AAAA0001", f)
    env.fix()
    other = env.file("other.pdf", b"54321")                # same size, other content
    os.utime(other, ns=(1_000_000_000, 1_000_000_000))
    state = json.loads(env.state.read_text())
    state["files"]["AAAA0001"]["ino"] = other.stat().st_ino
    env.state.write_text(json.dumps(state))
    f.unlink()
    report = env.fix()
    assert env.server.writes == [] and [m.reason for m in report.missing] == ["not found"]
