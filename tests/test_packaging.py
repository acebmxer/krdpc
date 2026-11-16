"""The packaging recipes agree with each other and with the code."""

import re
import subprocess
from pathlib import Path

import krdpc

ROOT = Path(__file__).resolve().parent.parent


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_the_version_script_reads_the_one_version_in_the_code():
    printed = subprocess.run(
        [ROOT / "scripts" / "package_version.sh"], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert printed == krdpc.__version__
    assert re.fullmatch(r"\d+\.\d+\.\d+", printed)


def test_no_recipe_hard_codes_the_version():
    # Each recipe takes the version from the build script; examples in comments are fine.
    assert "\nVersion:        %{krdpc_version}\n" in read("packaging/rpm/krdpc.spec")
    assert "\nVersion: @VERSION@\n" in read("packaging/deb/control.in")
    assert "\npkgver=${KRDPC_PKGVER:?" in read("packaging/arch/PKGBUILD")


def test_every_recipe_names_the_same_maintainer_homepage_and_licence():
    spec, control, pkgbuild = (
        read("packaging/rpm/krdpc.spec"),
        read("packaging/deb/control.in"),
        read("packaging/arch/PKGBUILD"),
    )
    assert "Maintainer: acebmxer\n" in control
    assert "PACKAGER=acebmxer" in read("packaging/arch/as-builder.sh")
    for recipe in (spec, control, pkgbuild):
        assert "https://github.com/acebmxer/krdpc" in recipe
    assert "License:        MIT" in spec and "license=('MIT')" in pkgbuild


def test_every_package_needs_freerdp_3_keyring_pyside6_and_svg_support():
    spec, control, pkgbuild = (
        read("packaging/rpm/krdpc.spec"),
        read("packaging/deb/control.in"),
        read("packaging/arch/PKGBUILD"),
    )
    assert "Requires:       freerdp >= 3.0" in spec and "qt6-qtsvg" in spec
    for needed in ("freerdp3-x11", "python3-keyring", "python3-pyside6.qtwidgets", "libqt6svg6"):
        assert needed in control
    for needed in ("'freerdp'", "'pyside6'", "'python-keyring'", "'qt6-svg'"):
        assert needed in pkgbuild


def test_the_files_the_packages_install_exist():
    for path in ("data/krdpc.desktop", "src/krdpc/krdpc.svg", "LICENSE", "CHANGELOG.md"):
        assert (ROOT / path).is_file(), path


def test_the_package_scripts_are_executable_and_start_with_a_shebang():
    for path in (
        "scripts/build_package.sh",
        "scripts/smoke_test.sh",
        "scripts/package_version.sh",
        "packaging/deb/postinst",
        "packaging/deb/prerm",
        "packaging/deb/krdpc.launcher",
    ):
        file = ROOT / path
        assert file.read_text().startswith("#!"), path
        assert file.stat().st_mode & 0o111, f"{path} is not executable"


def test_the_release_workflow_watches_the_version_file():
    workflow = read(".github/workflows/release.yml")
    assert 'paths: ["src/krdpc/__init__.py"]' in workflow
    for distro in ("fedora", "debian", "ubuntu", "arch"):
        assert distro in workflow
    # Only a manual run from dev makes a beta; main makes a draft.
    assert "--draft" in workflow and "--prerelease" in workflow


def test_every_package_is_told_its_release_and_format():
    # src/krdpc/updates.py reads RELEASE and FORMAT to find and install the next release.
    script = read("scripts/build_package.sh")
    assert "release=$version${beta:+-beta.$beta}" in script
    assert 'RELEASE = "%s"\\nFORMAT = "%s"' in script
    assert '"$release" "$format" >"$stamp/_package.py"' in script
    assert not (ROOT / "src" / "krdpc" / "_package.py").exists()
