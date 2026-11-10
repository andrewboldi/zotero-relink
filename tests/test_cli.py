"""Finding Zotero's files, reading credentials, and running zotlink from the command line."""
import json

from zotlink import cli, config


def make_db(env, tmp_path):
    """A Zotero data directory holding env's database."""
    data = tmp_path / "Zotero"
    data.mkdir()
    env.db.conn.commit()
    (data / "zotero.sqlite").write_bytes(env.db.path.read_bytes())
    return data


# ---- where Zotero keeps things ----

def test_finds_the_usual_data_directory(tmp_path):
    (tmp_path / "Zotero").mkdir()
    (tmp_path / "Zotero" / "zotero.sqlite").write_bytes(b"")
    assert config.find_data_dir(tmp_path, {}) == tmp_path / "Zotero"


def test_finds_the_snap_data_directory(tmp_path):
    d = tmp_path / "snap/zotero-snap/common/Zotero"
    d.mkdir(parents=True)
    (d / "zotero.sqlite").write_bytes(b"")
    assert config.find_data_dir(tmp_path, {}) == d


def test_a_custom_data_directory_in_zoteros_prefs_wins(tmp_path):
    (tmp_path / "Zotero").mkdir()
    (tmp_path / "Zotero" / "zotero.sqlite").write_bytes(b"")
    custom = tmp_path / "Research" / "ZoteroData"
    custom.mkdir(parents=True)
    (custom / "zotero.sqlite").write_bytes(b"")
    prefs = tmp_path / ".zotero/zotero/abcd1234.default/prefs.js"
    prefs.parent.mkdir(parents=True)
    prefs.write_text(f'user_pref("extensions.zotero.dataDir", "{custom}");\n'
                     f'user_pref("extensions.zotero.baseAttachmentPath", "{tmp_path}/Papers");\n')
    assert config.find_data_dir(tmp_path, {}) == custom
    assert config.find_base_dir(tmp_path) == tmp_path / "Papers"


def test_the_environment_variable_wins_over_everything(tmp_path):
    assert config.find_data_dir(tmp_path, {"ZOTERO_DATA_DIR": "/x/y"}) == config.Path("/x/y")


def test_credentials_come_from_the_env_file_or_the_environment(tmp_path):
    f = tmp_path / "env"
    f.write_text('# Zotero key\nZOTERO_API_KEY="abc123"\nZOTERO_USER_ID=42\n')
    assert config.credentials({}, f) == ("abc123", 42)
    assert config.credentials({"ZOTERO_API_KEY": "zzz", "ZOTERO_USER_ID": "7"}, f) == ("zzz", 7)
    assert config.credentials({}, tmp_path / "missing") is None


# ---- the command ----

def run(env, tmp_path, *args, api=None, capsys=None):
    data = make_db(env, tmp_path) if not (tmp_path / "Zotero").exists() else tmp_path / "Zotero"
    argv = ["--data-dir", str(data), "--root", str(env.home), "--state", str(env.state),
            "--env-file", str(tmp_path / "no-env-file"), "--trash-dir", str(env.trash), *args]
    environ = {"HOME": str(tmp_path)}
    if api:
        environ.update(ZOTERO_API_KEY="k", ZOTERO_USER_ID="1")
    code = cli.main(argv, make_api=(lambda key, uid: api) if api else None, environ=environ)
    return code, (capsys.readouterr().out if capsys else "")


def test_fix_relinks_a_renamed_file_and_says_so(env, tmp_path, capsys):
    f = env.file("a.pdf")
    env.link("AAAA0001", f)
    run(env, tmp_path, api=env.server, capsys=capsys)
    new = f.with_name("b.pdf")
    f.rename(new)
    code, out = run(env, tmp_path, api=env.server, capsys=capsys)
    assert code == 0 and env.server.path("AAAA0001") == str(new)
    assert "relinked 1" in out and str(new) in out


def test_fix_reads_a_copy_and_leaves_the_database_alone(env, tmp_path, capsys):
    env.link("AAAA0001", env.file("a.pdf"))
    data = make_db(env, tmp_path)
    before = (data / "zotero.sqlite").read_bytes()
    run(env, tmp_path, api=env.server, capsys=capsys)
    assert (data / "zotero.sqlite").read_bytes() == before
    assert sorted(p.name for p in data.iterdir()) == ["zotero.sqlite"]


def test_it_works_while_zotero_holds_its_lock_on_the_database(env, tmp_path, capsys):
    import sqlite3
    f = env.file("a.pdf")
    env.link("AAAA0001", f)
    data = make_db(env, tmp_path)
    run(env, tmp_path, api=env.server, capsys=capsys)
    f.rename(f.with_name("b.pdf"))
    zotero = sqlite3.connect(data / "zotero.sqlite", isolation_level=None)
    zotero.execute("BEGIN EXCLUSIVE")               # what a running Zotero does
    try:
        code, _ = run(env, tmp_path, api=env.server, capsys=capsys)
    finally:
        zotero.execute("ROLLBACK")
        zotero.close()
    assert code == 0 and env.server.path("AAAA0001") == str(f.with_name("b.pdf"))


def test_check_needs_no_key_and_changes_nothing(env, tmp_path, capsys):
    f = env.file("a.pdf")
    env.link("AAAA0001", f)
    run(env, tmp_path, api=env.server, capsys=capsys)
    f.rename(f.with_name("b.pdf"))
    code, out = run(env, tmp_path, "--dry-run", capsys=capsys)
    assert code == 0 and "would relink 1" in out and env.server.path("AAAA0001") == str(f)


def test_without_a_key_it_remembers_files_but_says_it_cannot_fix_them(env, tmp_path, capsys):
    f = env.file("a.pdf")
    env.link("AAAA0001", f)
    code, _ = run(env, tmp_path, capsys=capsys)
    assert code == 0 and env.state.exists()
    f.rename(f.with_name("b.pdf"))
    code, out = run(env, tmp_path, capsys=capsys)
    assert code == 2 and "ZOTERO_API_KEY" in out and env.server.path("AAAA0001") == str(f)


def test_quiet_runs_print_nothing_when_nothing_happened(env, tmp_path, capsys):
    env.link("AAAA0001", env.file("a.pdf"))
    code, out = run(env, tmp_path, "--quiet", api=env.server, capsys=capsys)
    assert code == 0 and out == ""


def test_status_shows_the_last_run(env, tmp_path, capsys):
    f = env.file("a.pdf")
    env.link("AAAA0001", f)
    run(env, tmp_path, api=env.server, capsys=capsys)
    f.unlink()
    run(env, tmp_path, api=env.server, capsys=capsys)
    code = cli.main(["status", "--state", str(env.state)])
    out = capsys.readouterr().out
    assert code == 0 and "AAAA0001" in out and "not found" in out


def test_every_relink_is_logged(env, tmp_path, capsys):
    f = env.file("a.pdf")
    env.link("AAAA0001", f)
    run(env, tmp_path, api=env.server, capsys=capsys)
    f.rename(f.with_name("b.pdf"))
    run(env, tmp_path, api=env.server, capsys=capsys)
    lines = [json.loads(line) for line in (env.state.parent / "log.jsonl").read_text().splitlines()]
    assert [(e["key"], e["old"], e["new"], e["how"]) for e in lines] == [
        ("AAAA0001", str(f), str(f.with_name("b.pdf")), "inode")]
