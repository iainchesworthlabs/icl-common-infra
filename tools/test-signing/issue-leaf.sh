#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Issue a code-signing leaf certificate from your personal CA, for test builds.
#
# Run this yourself, on the machine that holds the CA key. Never give the CA key, the leaf
# key or the PFX password to an assistant, a chat or CI. Only the leaf PFX (and its
# password) are uploaded, as organisation secrets. The CA key stays here.
#
#   issue-leaf.sh --ca-cert ca.crt --ca-key ca.key [--ca-key-pass-env VAR]
#                 [--cn "Iain Chesworth Labs Test Signing"] [--days 365]
#                 [--out-dir ./leaf-<yyyymmdd>] [--legacy-pfx]
#
# Produces in --out-dir:
#   leaf.key          private key (keep private, delete after the PFX is made if you wish)
#   leaf.crt          the certificate
#   leaf.pfx          leaf key + leaf cert + CA cert, password protected
#   leaf.pfx.b64      base64 of the PFX, for the secret WIN_TESTSIGN_PFX_BASE64
#   fingerprint.txt   SHA-256 fingerprint of the leaf, for the record
#
# The leaf has: CA:FALSE, keyUsage digitalSignature, extendedKeyUsage codeSigning
# (1.3.6.1.5.5.7.3.3), RSA 3072, validity <= 365 days.
#
# --legacy-pfx writes the PFX with the older 3DES/SHA1 protection, needed only for
# very old Windows versions. Current Windows (10 1809+, 11, Server 2019+) reads the
# default AES-256 protection.
#
# The PFX password is read from the prompt (or from the environment variable named by
# --pfx-pass-env) and is never printed.

set -euo pipefail

usage() { sed -n '4,30p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-2}"; }

ca_cert="" ca_key="" ca_key_pass_env="" pfx_pass_env=""
cn="Iain Chesworth Labs Test Signing"
days=365
out_dir=""
legacy=0

while [ $# -gt 0 ]; do
  case "$1" in
    --ca-cert) ca_cert="$2"; shift 2 ;;
    --ca-key) ca_key="$2"; shift 2 ;;
    --ca-key-pass-env) ca_key_pass_env="$2"; shift 2 ;;
    --pfx-pass-env) pfx_pass_env="$2"; shift 2 ;;
    --cn) cn="$2"; shift 2 ;;
    --days) days="$2"; shift 2 ;;
    --out-dir) out_dir="$2"; shift 2 ;;
    --legacy-pfx) legacy=1; shift ;;
    -h|--help) usage 0 ;;
    *) echo "unknown option: $1" >&2; usage ;;
  esac
done

[ -n "$ca_cert" ] && [ -n "$ca_key" ] || usage
[ -f "$ca_cert" ] || { echo "CA certificate not found: $ca_cert" >&2; exit 1; }
[ -f "$ca_key" ] || { echo "CA key not found: $ca_key" >&2; exit 1; }
case "$days" in ''|*[!0-9]*) echo "--days must be a number" >&2; exit 1 ;; esac
if [ "$days" -gt 365 ]; then echo "--days is limited to 365 so a leaked leaf expires quickly" >&2; exit 1; fi
command -v openssl >/dev/null || { echo "openssl is required" >&2; exit 1; }

[ -n "$out_dir" ] || out_dir="./leaf-$(date +%Y%m%d)"
if [ -e "$out_dir" ]; then echo "$out_dir already exists; choose another --out-dir" >&2; exit 1; fi
mkdir -p "$out_dir"
chmod 700 "$out_dir"
umask 077

if [ -n "$pfx_pass_env" ]; then
  [ -n "${!pfx_pass_env:-}" ] || { echo "environment variable $pfx_pass_env is empty" >&2; exit 1; }
  export ICL_PFX_PASS="${!pfx_pass_env}"
else
  read -r -s -p "PFX password (will be stored as WIN_TESTSIGN_PFX_PASSWORD): " p1; echo
  read -r -s -p "Repeat: " p2; echo
  [ "$p1" = "$p2" ] || { echo "passwords differ" >&2; exit 1; }
  [ "${#p1}" -ge 12 ] || { echo "use at least 12 characters" >&2; exit 1; }
  export ICL_PFX_PASS="$p1"
  unset p1 p2
fi

ca_pass_args=()
if [ -n "$ca_key_pass_env" ]; then
  [ -n "${!ca_key_pass_env:-}" ] || { echo "environment variable $ca_key_pass_env is empty" >&2; exit 1; }
  ca_pass_args=(-passin "env:$ca_key_pass_env")
fi

ext="$out_dir/leaf.ext"
cat > "$ext" <<EXT
basicConstraints = critical, CA:FALSE
keyUsage = critical, digitalSignature
extendedKeyUsage = critical, codeSigning
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid,issuer
EXT

openssl genrsa -out "$out_dir/leaf.key" 3072 2>/dev/null
openssl req -new -key "$out_dir/leaf.key" -subj "/CN=$cn" -out "$out_dir/leaf.csr"
openssl x509 -req -in "$out_dir/leaf.csr" -CA "$ca_cert" -CAkey "$ca_key" "${ca_pass_args[@]}" \
  -CAcreateserial -CAserial "$out_dir/ca.srl" -days "$days" -sha256 -extfile "$ext" -out "$out_dir/leaf.crt" 2>/dev/null

# Check the result before packaging it.
openssl verify -CAfile "$ca_cert" "$out_dir/leaf.crt" >/dev/null
openssl x509 -in "$out_dir/leaf.crt" -noout -text | grep -q "Code Signing" \
  || { echo "issued certificate lacks the Code Signing usage" >&2; exit 1; }

pfx_args=()
if [ "$legacy" -eq 1 ]; then pfx_args=(-legacy); fi
openssl pkcs12 -export "${pfx_args[@]}" -inkey "$out_dir/leaf.key" -in "$out_dir/leaf.crt" -certfile "$ca_cert" \
  -name "$cn" -passout env:ICL_PFX_PASS -out "$out_dir/leaf.pfx"
base64 -w0 "$out_dir/leaf.pfx" > "$out_dir/leaf.pfx.b64"
openssl x509 -in "$out_dir/leaf.crt" -noout -fingerprint -sha256 -enddate > "$out_dir/fingerprint.txt"
rm -f "$out_dir/leaf.csr" "$out_dir/leaf.ext" "$out_dir/ca.srl"
unset ICL_PFX_PASS

cat <<DONE

Issued: $out_dir/leaf.pfx
$(cat "$out_dir/fingerprint.txt")

Next, from this machine (the password is read from the prompt, not shown):

  gh secret set WIN_TESTSIGN_PFX_BASE64 --org iainchesworthlabs --visibility selected \\
     --repos <repo1>,<repo2> < "$out_dir/leaf.pfx.b64"
  gh secret set WIN_TESTSIGN_PFX_PASSWORD --org iainchesworthlabs --visibility selected \\
     --repos <repo1>,<repo2>

Then set the repository variable SIGN_WINDOWS to test. Renew before the date above.
Install the CA root on test machines as described in docs/test-signing.md.
DONE
