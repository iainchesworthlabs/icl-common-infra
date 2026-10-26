# Secrets and variables

The workflows read these names. Create them yourself; nobody else needs to see the values.
Organisation secrets are limited to the repositories that use them.

| Purpose | Names | Scope |
|---|---|---|
| GPG release signing | `REPO_GPG_PRIVATE_KEY`, `REPO_GPG_PASSPHRASE` | organisation |
| Release bot (fast-forwards `main`, bypasses the tag and `main` rulesets) | `RELEASE_BOT_APP_ID`, `RELEASE_BOT_PRIVATE_KEY` | organisation |
| Dependabot auto-merge | `MERGE_QUEUE_TOKEN`: fine-grained personal access token, Contents and Pull requests read and write on the repositories | organisation **Dependabot** secret |
| Windows test signing | `WIN_TESTSIGN_PFX_BASE64`, `WIN_TESTSIGN_PFX_PASSWORD` (see `docs/test-signing.md`) | organisation |
| Apple distribution | `IOS_DIST_CERT_P12_BASE64`, `IOS_DIST_CERT_PASSWORD`, `APPSTORE_API_KEY_ID`, `APPSTORE_API_ISSUER_ID`, `APPSTORE_API_PRIVATE_KEY` | organisation |
| iOS per app | `IOS_PROVISIONING_PROFILE_BASE64` | repository |
| macOS signing | `MACOS_DEVID_CERT_P12_BASE64`, `MACOS_DEVID_CERT_PASSWORD`, `NOTARY_API_KEY_ID`, `NOTARY_API_ISSUER_ID`, `NOTARY_API_PRIVATE_KEY` | organisation |
| Android upload key | `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD` | organisation |

Variables, set per repository by `admin/apply.sh` (all start as `false`):
`SIGN_WINDOWS` (`false`, `test`, `production`), `SIGN_MACOS`, `SIGN_IOS_UPLOAD`, `SIGN_IOS_ADHOC` (`true` builds the
ad-hoc IPA) and `IOS_IPA_ON_RELEASE` (`true` attaches it to the release). Neither of the last two is set by `apply.sh`.

Environment: `release`, with the owner as required reviewer. Created by `admin/apply.sh`.

## Release bot GitHub App

Create an organisation GitHub App with repository permission Contents: read and write and
nothing else, install it on the repositories that release, and put its id and private key in
the two secrets above. The `main-release-only` and `tags` rulesets name it as the bypass actor
(`admin/apply.sh` substitutes `RELEASE_BOT_APP_ID`).
