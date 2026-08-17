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
  // Mic-mute, tracked live by a read-only listener on vendor report 0x03.
  property bool micMuted: false

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
  implicitWidth: layout.implicitWidth
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

  // Persistent read-only listener for mic-mute state (never writes to the
  // device, so it cannot disturb the battery/vendor channel). Emits one JSON
  // line per state change: {"muted": true|false}.
  Process {
    id: micProc
    command: [root.pluginDir + "bin/hs80-mic-listen"]
    running: true
    stdout: SplitParser {
      onRead: (line) => {
        try {
          root.micMuted = JSON.parse(line).muted === true
        } catch (e) {
          // ignore malformed lines
        }
      }
    }
    onExited: micRestart.restart()
  }

  // If the listener ever exits (it self-heals internally, so this is rare),
  // bring it back after a short delay rather than tight-looping.
  Timer {
    id: micRestart
    interval: 3000
    onTriggered: micProc.running = true
  }

  Row {
    id: layout
    anchors.left: parent.left
    anchors.top: parent.top
    height: parent.height

    // Mic-mute glyph, rendered separately so it can be a couple px larger than
    // the battery text. Only shown once a mute event has been observed.
    Text {
      id: micGlyph
      visible: root.micMuted
      height: layout.height
      verticalAlignment: Text.AlignVCenter
      text: "\u{f036d}"  // 󰍭 mdi-microphone-off
      color: root.levelColor()
      font.family: button.fontFamily
      font.pixelSize: button.fontSize + 2
      renderType: Text.NativeRendering
      leftPadding: 6
      rightPadding: 0
    }

    WidgetButton {
      id: button
      bar: root.bar
      text: root.icon() + " " + (root.connected
        ? Math.round(root.percent) + "%"
        : (root.reconnecting ? "…" : "--"))
      foreground: root.levelColor()
      tooltipText: (root.micMuted ? "Mic muted • " : "") + (root.connected
        ? "Corsair HS80 Battery: " + Math.round(root.percent) + "%"
        : (root.reconnecting
          ? "Corsair HS80: reconnecting…"
          : "Corsair HS80: not connected"))
      onPressed: root.refresh()
    }
  }
}
