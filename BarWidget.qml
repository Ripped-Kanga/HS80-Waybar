import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

// Corsair HS80 battery widget: polls the bundled hidraw reader and shows a
// battery glyph plus percentage. Colors follow the theme — urgent when
// critical, blended toward urgent when low, dimmed while the headset is off.
BarWidget {
  id: root
  moduleName: "ripped-kanga.hs80-battery"

  readonly property string pluginDir: Qt.resolvedUrl(".").toString().replace(/^file:\/\//, "")
  readonly property int pollSeconds: Math.max(10, Number(setting("interval", 60)))
  readonly property bool hideWhenDisconnected: setting("hideWhenDisconnected", false) === true

  // -1 while the headset is powered off or out of range.
  property real percent: -1
  // "connected" | "reconnecting" | "disconnected"
  property string linkState: "disconnected"
  readonly property bool connected: linkState === "connected" && percent >= 0
  readonly property bool reconnecting: linkState === "reconnecting"

  readonly property color fg: bar ? bar.barForeground : Color.foreground
  readonly property color urgent: bar ? bar.urgent : Color.urgent

  function icon() {
    if (!connected) return "\u{f02ce}"
    if (percent >= 80) return "\u{f0942}"
    if (percent >= 60) return "\u{f0941}"
    if (percent >= 40) return "\u{f0940}"
    if (percent >= 20) return "\u{f093f}"
    return "\u{f093e}"
  }

  function levelColor() {
    if (reconnecting) return Qt.darker(fg, 1.25)
    if (!connected) return Qt.darker(fg, 1.55)
    if (percent <= 15) return urgent
    if (percent <= 30) return Qt.tint(fg, Qt.alpha(urgent, 0.55))
    return fg
  }

  function refresh() {
    if (!proc.running) proc.running = true
  }

  visible: connected || reconnecting || !hideWhenDisconnected
  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  IpcHandler {
    target: "ripped-kanga.hs80-battery"

    function refresh(): void {
      root.broadcast("refresh")
    }
  }

  Process {
    id: proc
    command: [root.pluginDir + "bin/hs80-battery"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try {
          var status = JSON.parse(text)
          var pct = Number(status.percentage)
          root.percent = isFinite(pct) ? pct : -1
          // Fall back to inferring state from percentage for older poller output.
          root.linkState = status.state
            || (isFinite(pct) ? "connected" : "disconnected")
        } catch (e) {
          root.percent = -1
          root.linkState = "disconnected"
        }
      }
    }
  }

  Timer {
    interval: root.pollSeconds * 1000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: root.refresh()
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.icon() + " " + (root.connected
      ? Math.round(root.percent) + "%"
      : (root.reconnecting ? "…" : "--"))
    foreground: root.levelColor()
    tooltipText: root.connected
      ? "Corsair HS80 Battery: " + Math.round(root.percent) + "%"
      : (root.reconnecting
        ? "Corsair HS80: reconnecting…"
        : "Corsair HS80: not connected")
    onPressed: root.refresh()
  }
}
