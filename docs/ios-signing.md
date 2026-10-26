# Signing an iOS build

A project builds a signed iPhone and iPad application with two actions of this repository, on a macOS runner:
`import-ios-signing` (the certificate and the profile) and `export-ios-ipa` (`xcodebuild archive`, the export, and an
optional manifest for an install over the air). They are the steps that CountdownSolver ran first, kept in one place
(standard D8, D16 and section 13).

Ad hoc means the build installs only on the devices that the provisioning profile lists. There is no App Store and no
TestFlight in it. Distribution through the store is the same actions with `method: app-store`, and an upload step that
is not written yet.

## What is shared and what is the project's

| | Where | Why |
|---|---|---|
| Apple Distribution certificate (`IOS_DIST_CERT_P12_BASE64`) and its password (`IOS_DIST_CERT_PASSWORD`) | organisation secrets, restricted to the repositories that build for iOS | One certificate signs every app of the team |
| Provisioning profile (`IOS_PROVISIONING_PROFILE_BASE64`) | repository secret | A profile belongs to one App ID, and an ad-hoc one to a list of devices |
| The bundle identifier, the scheme, the file names | the project's workflow | |
| Team ID and the profile's name | not secrets: read out of the profile | Fewer values to keep in step |

## Getting the pieces from Apple

1. *Devices*: register each iPhone or iPad. A device's UDID is in Finder (select the device and click the line under its
   name until the UDID shows) or in Xcode's *Devices and Simulators* window.
2. *Identifiers*: register an explicit App ID for the project's bundle identifier.
3. *Profiles*: make an **Ad Hoc** profile for that App ID, with the Apple Distribution certificate and the devices.
   Download the `.mobileprovision`.
4. Export the certificate from Keychain Access as a `.p12`, **with its private key**, and give it a password.

```sh
base64 -w0 dist.p12 | gh secret set IOS_DIST_CERT_P12_BASE64 --org iainchesworthlabs --visibility selected --repos <repo>,<repo>
printf '%s' 'the .p12 password' | gh secret set IOS_DIST_CERT_PASSWORD --org iainchesworthlabs --visibility selected --repos <repo>,<repo>
base64 -w0 app.mobileprovision | gh secret set IOS_PROVISIONING_PROFILE_BASE64 -R iainchesworthlabs/<repo>
```

An organisation secret can only reach a repository of the organisation. A project that is still under a personal account
sets all three as repository secrets until it moves.

## Adding a device

A device installs only builds signed with a profile that lists it. Register the device, edit the ad-hoc profile to include
it, download it, set `IOS_PROVISIONING_PROFILE_BASE64` again and build again. A build made before the device was added
never installs on it. A profile lasts a year.

## Using the actions

```yaml
- uses: iainchesworthlabs/icl-common-infra/actions/import-ios-signing@<commit>
  id: signing
  with:
    certificate-base64: ${{ secrets.IOS_DIST_CERT_P12_BASE64 }}
    certificate-password: ${{ secrets.IOS_DIST_CERT_PASSWORD }}
    profile-base64: ${{ secrets.IOS_PROVISIONING_PROFILE_BASE64 }}
    bundle-id: io.github.example.app

# The project's own configure line gives the team and the profile name to CMake (signing the application target alone).
- run: cmake --preset ios-release -DEXAMPLE_IOS_SIGNING_TEAM=${{ steps.signing.outputs.team-id }} "-DEXAMPLE_IOS_SIGNING_PROFILE=${{ steps.signing.outputs.profile-name }}" -DCMAKE_XCODE_GENERATE_SCHEME=ON

- uses: iainchesworthlabs/icl-common-infra/actions/export-ios-ipa@<commit>
  with:
    project: build/ios-release/Example.xcodeproj
    scheme: example
    bundle-id: io.github.example.app
    team-id: ${{ steps.signing.outputs.team-id }}
    profile-name: ${{ steps.signing.outputs.profile-name }}
    output: dist/Example-ios-adhoc.ipa

- if: always()
  uses: iainchesworthlabs/icl-common-infra/actions/import-ios-signing@<commit>
  with:
    remove: "true"
```

Two lessons from the projects that did this first: sign the application target alone (project-wide signing makes Xcode
sign static libraries and Qt's resource bundles, which have no bundle identifier), and ask CMake to generate the scheme
(`xcodebuild archive` takes a scheme, and CMake makes none by default).

## An IPA in a public repository

An ad-hoc IPA contains its provisioning profile, and the profile lists the UDIDs of the devices. Attaching it to a public
release publishes them. A UDID is not a credential, but it identifies a device. A public project decides this on purpose:
attach the IPA to the release, or keep it as a workflow artifact and install it from a computer.
