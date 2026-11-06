#!/usr/bin/env bash
# One-time tool setup for a fresh cloud container (also usable as the
# environment's setup script). Idempotent: safe to run again.
# Installs: tesseract + heb (fast) + tessdata_best heb, hunspell-he, epubcheck,
# pandoc, poppler, imagemagick, and the David Libre font.
# Tools land in standard paths; tessdata_best and the font go to $EPUB_TOOLS
# (default ~/.epub-tools).
set -euo pipefail
TOOLS=${EPUB_TOOLS:-$HOME/.epub-tools}
SUDO=$([ "$(id -u)" = 0 ] && echo "" || echo sudo)

need=()
for c in tesseract hunspell pandoc pdftoppm convert java curl; do
  command -v "$c" >/dev/null || need+=("$c")
done
[ -f /usr/share/hunspell/he_IL.dic ] || need+=(hunspell-he)
find /usr/share -name heb.traineddata -path '*tessdata*' 2>/dev/null | grep -q . || need+=(tesseract-ocr-heb)
[ -f /usr/bin/epubcheck ] || need+=(epubcheck)

if [ ${#need[@]} -gt 0 ]; then
  # apt in the cloud container ignores the proxy and uses http sources.
  if [ -n "${HTTPS_PROXY:-}" ] && [ ! -f /etc/apt/apt.conf.d/99proxy ]; then
    [[ "$HTTPS_PROXY" =~ ^https?://[^[:space:]\"\;]+$ ]] || { echo "unexpected HTTPS_PROXY format" >&2; exit 1; }
    $SUDO install -m 600 /dev/null /etc/apt/apt.conf.d/99proxy
    printf 'Acquire::http::Proxy "%s";\nAcquire::https::Proxy "%s";\n' "$HTTPS_PROXY" "$HTTPS_PROXY" |
      $SUDO tee /etc/apt/apt.conf.d/99proxy >/dev/null
    [ -f /etc/apt/sources.list.d/ubuntu.sources ] &&
      $SUDO sed -i 's|http://|https://|g' /etc/apt/sources.list.d/ubuntu.sources
    [ -f /etc/apt/sources.list.d/docker.list ] &&
      $SUDO mv /etc/apt/sources.list.d/docker.list /etc/apt/docker.list.disabled
  fi
  $SUDO apt-get update -qq
  DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y -qq \
    tesseract-ocr tesseract-ocr-heb tesseract-ocr-eng hunspell hunspell-he \
    epubcheck pandoc poppler-utils imagemagick default-jre-headless curl >/dev/null
fi

python3 -c "import cv2, numpy, PIL" 2>/dev/null ||
  python3 -m pip install -q opencv-python-headless numpy pillow 2>/dev/null ||
  { echo "error: could not install cv2/numpy/Pillow for $(command -v python3)" >&2; exit 1; }

mkdir -p "$TOOLS/tessdata" "$TOOLS/fonts"
if [ ! -f "$TOOLS/tessdata/heb.traineddata" ]; then
  curl -sSfL --connect-timeout 20 --max-time 300 --retry 3 -o "$TOOLS/tessdata/heb.traineddata" \
    https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/main/heb.traineddata
  # tsv output silently falls back to txt without these next to the model
  sys=$(dirname "$(find /usr/share -name eng.traineddata -path '*tessdata*' | head -1)")
  cp -r "$sys/configs" "$sys/tessconfigs" "$TOOLS/tessdata/"
fi
[ -f "$TOOLS/tessdata/configs/tsv" ] || { echo "error: tesseract configs missing in $TOOLS/tessdata" >&2; exit 1; }
for f in DavidLibre-Regular DavidLibre-Bold; do
  [ -f "$TOOLS/fonts/$f.ttf" ] || curl -sSfL --connect-timeout 20 --max-time 120 --retry 3 -o "$TOOLS/fonts/$f.ttf" \
    "https://raw.githubusercontent.com/google/fonts/main/ofl/davidlibre/$f.ttf"
done
echo "ready: tessdata_best=$TOOLS/tessdata fonts=$TOOLS/fonts"
