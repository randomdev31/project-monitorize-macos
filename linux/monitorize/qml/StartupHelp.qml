import QtQuick
import QtQuick.Controls

ToolButton {
    id: control
    required property string helpText
    text: "?"
    Accessible.name: helpText
    ToolTip.visible: hovered
    ToolTip.text: helpText
    onClicked: helpPopup.open()
    Popup {
        id: helpPopup
        width: Math.min(360, control.Window.window ? control.Window.window.width - 32 : 360)
        x: control.width - width
        y: control.height
        padding: 12
        contentItem: Text { text: control.helpText; color: theme.textPrimary; wrapMode: Text.WordWrap }
        background: Rectangle { color: theme.surface; border.color: theme.border; radius: theme.controlRadius }
    }
}
