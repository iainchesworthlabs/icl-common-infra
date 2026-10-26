# Signing an iOS build

A project builds a signed iPhone and iPad application with two actions of this repository, on a macOS runner:
`import-ios-signing` (the certificate and the profile) and `export-ios-ipa` (`xcodebuild archive`, the export, and an
optional manifest for an install over the air). They are the steps that CountdownSolver ran first, kept in one place
(standard D8, D16 and section 13).

**Status.** Snake ran this end to end on a hosted macOS runner: import, signed configure, archive, export and a check of
the IPA's signature and profile (release workflow run 40272693096, snake). CountdownSolver ran the same steps first and has
an IPA installed on a device. Neither Snake's IPA nor these actions have been installed on a device yet.

Ad hoc means the build installs only on the devices that the provisioning profile lists. There is no App Store and no
TestFlight in it. Distribution through the store is the same actions with `method: app-store`, and an upload step that
is not written yet.

## What is shared and what is the project's

| | Where | Why |
|---|---|---|
| Apple Distribution certificate (`IOS_DIST_CERT_P12_BASE64`) and its password (`IOS_DIST_CERT_PASSWORD`) | organisation secrets, restricted to the repositories that build for iOS | One certificate signs every app of the team |
| Provisioning profile (`IOS_PROVISIONING_PROFILE_BASE64`) | repository secret | A profile belongs to one App ID, and an ad-hoc one to a list of devices |
| The bundle identifier, the scheme, the file names | the project's workflow | |

The bundle identifier is **`com.iainchesworthlabs.<app>`**, the same string as the Android application id, and it is what
you register as the App ID. `import-ios-signing` refuses a profile whose App ID is not `<team>.<bundle id>` and says so, so
a mismatch stops the build in its first step.
| Team ID and the profile's name | not secrets: read out of the profile | Fewer values to keep in step |

## Getting the pieces from Apple

1. *Devices*: register each iPhone or iPad. A device's UDID is in Finder (select the device and click the line under its
   name until the UDID shows) or in Xcode's *Devices and Simulators* window.
2. *Identifiers*: register an explicit App ID for the project's bundle identifier.
3. *Profiles*: make an **Ad Hoc** profile for that App ID, with the Apple Distribution certificate and the devices.
   Download the `.mobileprovision`.
4. Export the certificate from Keychain Access as a `.p12`, **with its private key**, and give it a password. If the
   `.p12` came from OpenSSL 3, make it in the legacy encoding (`openssl pkcs12 -export -legacy ...`): the older `security`
   tool of a runner's macOS may refuse the new one. To check which certificate a `.p12` holds, without printing a secret:
   `openssl pkcs12 -legacy -in dist.p12 -nokeys -clcerts | openssl x509 -noout -fingerprint -sha256 -enddate` and compare
   the fingerprint with the one in the profile. (`grep -c 'PRIVATE KEY'` on the key counts two lines for one key.)

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

## In the project

- **CMake.** Two cache variables, empty by default, and signing set on the application target when both are given (the
  presets turn signing off project-wide):

  ```cmake
  set(APP_IOS_SIGNING_TEAM "" CACHE STRING "Apple team ID (empty: an unsigned build)")
  set(APP_IOS_SIGNING_PROFILE "" CACHE STRING "Provisioning profile name (empty: an unsigned build)")
  # ... after the target's MACOSX_BUNDLE properties:
  if(APP_IOS_SIGNING_TEAM AND APP_IOS_SIGNING_PROFILE)
      set_target_properties(app PROPERTIES
          XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED "YES"
          XCODE_ATTRIBUTE_CODE_SIGNING_REQUIRED "YES"
          XCODE_ATTRIBUTE_CODE_SIGN_STYLE "Manual"
          XCODE_ATTRIBUTE_CODE_SIGN_IDENTITY "Apple Distribution"
          XCODE_ATTRIBUTE_DEVELOPMENT_TEAM "${APP_IOS_SIGNING_TEAM}"
          XCODE_ATTRIBUTE_PROVISIONING_PROFILE_SPECIFIER "${APP_IOS_SIGNING_PROFILE}")
  endif()
  ```

- **The scheme is the CMake target's name**, not the name of the file it makes: a target `snake_app` with
  `OUTPUT_NAME snake` has the scheme `snake_app`. Snake's first signed run failed on this.
- **The release job.** Snake's `ios` job in `release.yml` is the worked example: it runs only when `SIGN_IOS_ADHOC` is
  `true`, imports the signing, configures with `-DCMAKE_XCODE_GENERATE_SCHEME=ON` and the team and profile name, finds the
  `.xcodeproj`, exports, checks the IPA, removes the keychain in a step with `if: always()`, and uploads the IPA. The upload is
  named `release-ios-adhoc` (picked up by `release-publish.yml`'s `release-*` pattern, so it is signed, attested and listed with
  the other files) only when `IOS_IPA_ON_RELEASE` is `true`, and `ios-adhoc` (a workflow artifact, not published) otherwise.
  The `publish` job lists the iOS job in `needs` and accepts it being skipped.
- **A check of the IPA** (`verify_app.sh --signed` in Snake) is worth having: the identifier, the version, no usage text for
  a permission the app does not use, arm64, a valid signature, and a profile that is ad hoc and belongs to this identifier.

Two lessons from the projects that did this first: sign the application target alone (project-wide signing makes Xcode
sign static libraries and Qt's resource bundles, which have no bundle identifier), and ask CMake to generate the scheme
(`xcodebuild archive` takes a scheme, and CMake makes none by default).

## An IPA in a public repository

An ad-hoc IPA contains its provisioning profile, and the profile lists the UDIDs of the devices. Attaching it to a public
release publishes them. A UDID is not a credential, but it identifies a device. A public project decides this on purpose:
attach the IPA to the release (`IOS_IPA_ON_RELEASE=true`), or keep it as a workflow artifact and install it from a computer.
An install over the air needs an HTTPS page with an `itms-services://` link to the manifest, which GitHub Pages can host.

## Projects that have their own job

CountdownSolver's job is the one these actions come from, and wordjewelssolver has one that has not run. Both use the secret
names `IOS_DIST_CERTIFICATE_BASE64` and `IOS_DIST_CERTIFICATE_PASSWORD`, and two more, `APPLE_TEAM_ID` and
`APPLE_PROVISIONING_PROFILE_NAME`. When they join the organisation they take the names above, drop the last two (the action
reads them out of the profile) and replace the job's signing steps with the two actions.
