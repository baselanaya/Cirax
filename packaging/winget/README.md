# winget manifests for Cirax

These manifests make `winget install BaselAnaya.Cirax` possible. They are
submitted to the community repo — there is no review from Microsoft needed
for the manifests themselves beyond the standard PR checks.

## Submit (once per release)

1. Bump `Version:` in all three `.yaml` files to the new version and point
   `InstallerUrl` at the new `Cirax-Setup-<ver>-win64.exe` release asset.
2. Update `InstallerSha256` with the hash of the new installer
   (`Get-FileHash` on Windows, `sha256sum` elsewhere).
3. Clone https://github.com/microsoft/winget-pkgs, copy the folder as
   `manifests/b/BaselAnaya/Cirax/<version>/`, push to your fork, open a PR
   titled `Add version: BaselAnaya.Cirax <version>`.
4. After the PR merges, `winget install BaselAnaya.Cirax` works.

Quick local generation of a new version's files:
`pwsh packaging/windows/update-winget.ps1 <version> <sha256>` (optional helper).
