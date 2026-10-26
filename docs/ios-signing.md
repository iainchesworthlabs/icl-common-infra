# Signing an iOS build

A project builds a signed iPhone and iPad application with two actions of this repository, on a macOS runner:
`import-ios-signing` (the certificate and the profile) and `export-ios-ipa` (`xcodebuild archive`, the export, and an
optional manifest for an install over the air). They are the steps that CountdownSolver ran first, kept in one place
(standard D8, D16 and section 13).

**Status.** Snake ran this end to end on a hosted macOS runner: import, signed configure, archive, export and a check of
the IPA's signature and profile (release workflow run 40272693096, snake). CountdownSolver ran the same steps first and has
an IPA installed on a device. Neither Snake's IPA nor these actions have been installed on a device yet.

There are two ways to get a build onto a device, and the same two actions make either:

- **TestFlight** (`method: app-store`, then `upload-testflight`): the build goes to Apple, and the testers install it from
  the TestFlight app. No device is registered, no UDID is in the build, nothing is hosted by the project. This is the
  way for a public repository. See [TestFlight](#testflight).
- **Ad hoc** (`method: ad-hoc`): the build installs only on the devices that the provisioning profile lists, and the
  project has to hand the IPA over, for example with an `itms-services://` link to an HTTPS page. The IPA contains the
  profile, which lists the devices' UDIDs (see [An IPA in a public repository](#an-ipa-in-a-public-repository)).

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

## TestFlight

Once per account, in App Store Connect and the developer portal:

1. Accept the Apple Developer Program License Agreement if a banner asks. A free app needs no Paid Apps agreement.
2. *Apps*, then *New App*: iOS, the bundle identifier of the project, a name that is **unique across the App Store** (it
   is only the store name: the name under the icon comes from the app), a language, and any SKU.
3. *Profiles*, then *Distribution*, then **App Store Connect**: for the project's App ID and the Apple Distribution
   certificate. It lists no devices. This is the project's `IOS_PROVISIONING_PROFILE_BASE64`.
4. *Users and Access*, then *Integrations*, then *App Store Connect API*, then *Team Keys*, then +, with the role **App
   Manager**. Download the `.p8` once; note the Key ID and the Issuer ID (shown above the list).
5. Organisation secrets, restricted to the projects that use them:
   `APPSTORE_API_KEY_ID`, `APPSTORE_API_ISSUER_ID` and `APPSTORE_API_PRIVATE_KEY` (the contents of the `.p8`):

   ```sh
   gh secret set APPSTORE_API_KEY_ID --org iainchesworthlabs --visibility selected --repos <repo>,<repo>
   gh secret set APPSTORE_API_ISSUER_ID --org iainchesworthlabs --visibility selected --repos <repo>,<repo>
   gh secret set APPSTORE_API_PRIVATE_KEY --org iainchesworthlabs --visibility selected --repos <repo>,<repo> < AuthKey_XXXX.p8
   ```

6. In the app's *TestFlight* tab, make an *Internal Testing* group and add the testers (people with an App Store Connect
   login, up to 100). Internal builds are available as soon as Apple has processed them, with no Beta App Review. Each
   tester installs the TestFlight app and signs in with the same Apple ID.

In the project's release job, `import-ios-signing` and `export-ios-ipa` take `method: app-store`, and then:

```yaml
- uses: iainchesworthlabs/icl-common-infra/actions/upload-testflight@<commit>
  with:
    ipa: dist/Example.ipa
    key-id: ${{ secrets.APPSTORE_API_KEY_ID }}
    issuer-id: ${{ secrets.APPSTORE_API_ISSUER_ID }}
    private-key: ${{ secrets.APPSTORE_API_PRIVATE_KEY }}
    validate-only: ${{ github.ref_type != 'tag' }}   # Apple's own check; nothing uploaded
```

Apple refuses a build whose **build number** (`CFBundleVersion`) is not higher than every earlier one for that version:
give the CMake build a build number from the workflow run number. The property list also needs
`ITSAppUsesNonExemptEncryption` (otherwise TestFlight asks about encryption for every build), a 1024 pixel icon without
transparency, and `UIRequiresFullScreen` for an iPad app that is not available in every orientation. Validate first
(`validate-only: true`): Apple's checks name what is wrong, such as the icon or the privacy declarations of the libraries.

## Adding a device (ad hoc only)

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
release publishes them. A UDID is not a credential, but it identifies a device. Neither a release asset nor a workflow artifact is private in a public repository: any signed-in GitHub account can
download an artifact. GitHub Pages cannot be put behind a login on the Free plan, and an install over the air cannot be put
behind one either, because iOS fetches the manifest and the IPA itself, without cookies or a login. A public project that
cannot accept this uses TestFlight.

## Projects that have their own job

CountdownSolver's job is the one these actions come from, and wordjewelssolver has one that has not run. Both use the secret
names `IOS_DIST_CERTIFICATE_BASE64` and `IOS_DIST_CERTIFICATE_PASSWORD`, and two more, `APPLE_TEAM_ID` and
`APPLE_PROVISIONING_PROFILE_NAME`. When they join the organisation they take the names above, drop the last two (the action
reads them out of the profile) and replace the job's signing steps with the two actions.
