"""gr-prepare with the game's update in a folder of its own (--update)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "prepare"))
import gr_prepare  # noqa: E402


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_the_update_s_files_replace_the_game_s(tmp_path):
    game, update, data = tmp_path / "CUSA04943", tmp_path / "CUSA04943-patch", tmp_path / "data"
    for name in ("eboot.bin", "sce_sys/param.sfo", "sce_module/libc.prx", "sce_module/libSceFios2.prx"):
        write(game / name, "game " + name)
    for name in ("eboot.bin", "sce_sys/param.sfo", "sce_module/libSceFios2.prx", "sce_module/new.prx"):
        write(update / name, "update " + name)
    view = gr_prepare.game_view(game, update, data)
    assert (view / "eboot.bin").read_text() == "update eboot.bin"
    assert (view / "sce_sys/param.sfo").read_text() == "update sce_sys/param.sfo"
    assert (view / "sce_module/libc.prx").read_text() == "game sce_module/libc.prx"
    assert (view / "sce_module/libSceFios2.prx").read_text() == "update sce_module/libSceFios2.prx"
    assert gr_prepare.modules(view) == ["libc.prx", "libSceFios2.prx", "new.prx"]
    assert (game / "eboot.bin").read_text() == "game eboot.bin"  # the game folder is untouched


def test_an_update_without_the_game_is_refused(tmp_path, capsys):
    update, data = tmp_path / "CUSA04943-patch", tmp_path / "data"
    write(update / "eboot.bin", "e")
    write(update / "sce_sys/param.sfo", "s")
    assert gr_prepare.main([str(update), str(data), str(tmp_path / "rt.exe")]) == 1
    assert "libc.prx" in capsys.readouterr().out
