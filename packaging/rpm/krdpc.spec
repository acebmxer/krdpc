# Built by scripts/build_package.sh with:
#   --define "krdpc_version <rpm version>"         0.1.0, or 0.1.0~beta.1 for a beta
#   --define "krdpc_source_version <code version>" the version in src/krdpc/__init__.py
Name:           krdpc
Version:        %{krdpc_version}
Release:        1%{?dist}
Summary:        A KDE app that keeps a list of remote computers and opens each with FreeRDP
License:        MIT
URL:            https://github.com/acebmxer/krdpc
Source0:        krdpc-%{krdpc_source_version}.tar.gz
BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  pyproject-rpm-macros
BuildRequires:  desktop-file-utils

# xfreerdp is in the freerdp package. krdpc needs FreeRDP 3 (its /cert: options).
Requires:       freerdp >= 3.0
Requires:       qt6-qtsvg

%description
krdpc is a small native KDE desktop app, laid out like Remmina's main window. It
keeps a list of your remote computers, asks for the password (or remembers it in
KDE Wallet) and opens each one with FreeRDP's xfreerdp. It is not an RDP engine.

%prep
%autosetup -n krdpc-%{krdpc_source_version}

%generate_buildrequires
%pyproject_buildrequires -R

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files krdpc
install -Dpm 0644 data/krdpc.desktop %{buildroot}%{_datadir}/applications/krdpc.desktop
install -Dpm 0644 src/krdpc/krdpc.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/krdpc.svg

%check
desktop-file-validate %{buildroot}%{_datadir}/applications/krdpc.desktop

%files -f %{pyproject_files}
%license LICENSE
%doc README.md CHANGELOG.md
%{_bindir}/krdpc
%{_datadir}/applications/krdpc.desktop
%{_datadir}/icons/hicolor/scalable/apps/krdpc.svg

%changelog
* Sun Nov 15 2026 acebmxer - 0.1.0-1
- First release. See CHANGELOG.md.
