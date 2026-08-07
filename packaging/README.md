# Packaging

## Conda packaging

recipe.yaml

## Windows installer

- `build.ps1`: assembles the embedded Python environment, application files, and launcher, then invokes Inno Setup.
- `beratools.iss`: defines the installer layout and Windows version metadata.
- `main.go`: builds the Windows GUI launcher included in the installer.

## Build locally

Run the following command to build the Windows installer locally:

```powershell
.\build.ps1
```

This generates the installer in the `dist` directory. The `build` folder stores temporary files created during the build process.

Local builds are unsigned. Official installers are built and signed by the [Build Windows Installer workflow](../.github/workflows/build-win-installer.yml); no signing certificate or private key is stored in this repository. See [Windows Installer Signing](../docs/files/developer/publishing.md#windows-installer-signing) for manual test signing and production release instructions, and see the project [Code signing policy](../CODE_SIGNING_POLICY.md) for signing roles and privacy commitments.
