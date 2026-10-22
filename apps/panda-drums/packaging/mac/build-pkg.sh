#!/bin/bash
# Builds the Mac installer from the built plugins:
#   packaging/mac/build-pkg.sh <artefacts dir> <version> <output .pkg>
# The artefacts dir is build/PandaDrums_artefacts/Release (AU/, VST3/, Standalone/ inside).
# One .pkg, three ticked boxes: Audio Unit, VST3 and the stand-alone app.
set -euo pipefail

art="$1"
version="$2"
out="$3"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

component() {
    local id="$1" bundle="$2" dest="$3"
    mkdir -p "$work/$id/root"
    cp -R "$bundle" "$work/$id/root/"
    # Install exactly where we say, even if an old copy sits somewhere else on the disk.
    pkgbuild --analyze --root "$work/$id/root" "$work/$id/components.plist" >/dev/null
    plutil -replace 0.BundleIsRelocatable -bool NO "$work/$id/components.plist"
    pkgbuild --root "$work/$id/root" --component-plist "$work/$id/components.plist" \
             --identifier "com.thepandastudios.pandadrums.$id" --version "$version" \
             --install-location "$dest" "$work/$id.pkg"
}

component au   "$art/AU/Panda Drums.component" "/Library/Audio/Plug-Ins/Components"
component vst3 "$art/VST3/Panda Drums.vst3"    "/Library/Audio/Plug-Ins/VST3"
component app  "$art/Standalone/Panda Drums.app" "/Applications"

cat > "$work/distribution.xml" <<XML
<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="2">
    <title>Panda Drums $version</title>
    <options customize="allow" require-scripts="false" hostArchitectures="arm64,x86_64"/>
    <allowed-os-versions><os-version min="10.13"/></allowed-os-versions>
    <domains enable_localSystem="true"/>
    <choices-outline>
        <line choice="au"/>
        <line choice="vst3"/>
        <line choice="app"/>
    </choices-outline>
    <choice id="au" title="Audio Unit" description="For Logic Pro, GarageBand and other AU hosts.">
        <pkg-ref id="com.thepandastudios.pandadrums.au"/>
    </choice>
    <choice id="vst3" title="VST3" description="For Ableton Live, Studio One, Cubase, Reaper, FL Studio and others.">
        <pkg-ref id="com.thepandastudios.pandadrums.vst3"/>
    </choice>
    <choice id="app" title="Stand-alone app" description="Panda Drums on its own, in Applications.">
        <pkg-ref id="com.thepandastudios.pandadrums.app"/>
    </choice>
    <pkg-ref id="com.thepandastudios.pandadrums.au" version="$version">au.pkg</pkg-ref>
    <pkg-ref id="com.thepandastudios.pandadrums.vst3" version="$version">vst3.pkg</pkg-ref>
    <pkg-ref id="com.thepandastudios.pandadrums.app" version="$version">app.pkg</pkg-ref>
</installer-gui-script>
XML

productbuild --distribution "$work/distribution.xml" --package-path "$work" "$out"
echo "built $out"
