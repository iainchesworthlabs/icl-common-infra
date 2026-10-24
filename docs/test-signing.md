# Test signing for Windows builds

Test builds are signed with a leaf certificate issued by a personal certificate authority
(CA). They are trusted only on machines that have that CA's root installed. Until a
production certificate exists, a release may carry `*-testsigned` files, final or
pre-release; its notes and verification page say they are test-signed. When a production
signing service is chosen, `SIGN_WINDOWS` changes to `production` and this document is
replaced.

The `sign-windows` action renames each file it handles to `NAME-unsigned.EXT` or
`NAME-testsigned.EXT`. A project whose programs sit inside a package under their own names
passes `rename: false` and puts the action's `suffix` output on the package file instead.

## What goes where

| Item | Where it lives |
|---|---|
| CA private key | Offline, on the owner's machine. Never uploaded, never shared with an assistant. |
| CA certificate (public) | Installed on test machines. May be published. |
| Leaf private key and certificate, as `leaf.pfx` | Organisation secret `WIN_TESTSIGN_PFX_BASE64` (base64), password in `WIN_TESTSIGN_PFX_PASSWORD` |
| Mode | Repository variable `SIGN_WINDOWS` (`false`, `test`, `production`) |

## Issue a leaf certificate

Run `tools/test-signing/issue-leaf.sh` from this repository on the machine that holds the
CA key:

```bash
tools/test-signing/issue-leaf.sh --ca-cert ca.crt --ca-key ca.key
```

The leaf has `CA:FALSE`, key usage `digitalSignature`, extended key usage Code Signing
(1.3.6.1.5.5.7.3.3), RSA 3072, and a validity of at most 365 days. The script prompts for
the PFX password, verifies the leaf against the CA, and writes `leaf.pfx` and
`leaf.pfx.b64` to a new directory. It prints the two `gh secret set` commands to upload them.
Renew before the printed expiry date. Signatures carry an RFC 3161 timestamp, so files
signed before expiry stay valid after it.

## Install the CA root on a test machine

Windows, from an elevated PowerShell:

```powershell
Import-Certificate -FilePath ca.crt -CertStoreLocation Cert:\LocalMachine\Root
```

Other machines, and Windows SmartScreen, will not trust the build. That is the expected
behaviour for a test certificate.

## Check a signed file

```powershell
Get-AuthenticodeSignature .\app-testsigned.exe | Format-List Status, SignerCertificate, TimeStamperCertificate
```

On a machine with the CA root installed, `Status` is `Valid`. Without it, `Status` is
`UnknownError` or `NotTrusted` and the signer and timestamp certificates are still present.

## Move to production

Set the secrets for the chosen service, change `SIGN_WINDOWS` to `production`, and add the
service's signing step to `.github/actions/sign-windows` (the steps for `signtool` stay the
same where the service is a certificate with a cloud-held key).
