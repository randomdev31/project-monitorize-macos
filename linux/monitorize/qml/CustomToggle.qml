import QtQuick
import QtQuick.Controls

Switch {
    id: toggle

    spacing: 10
    implicitHeight: 30
    hoverEnabled: true

    indicator: Rectangle {
        implicitWidth: 42
        implicitHeight: 22
        x: toggle.leftPadding
        y: parent.height / 2 - height / 2
        radius: height / 2
        color: !toggle.enabled ? theme.surfaceAlt : toggle.checked
            ? (toggle.hovered || toggle.down ? theme.buttonBackgroundHover : theme.buttonBackground)
            : theme.surfaceAlt
        border.color: !toggle.enabled ? theme.border : toggle.checked
            ? (toggle.hovered || toggle.down ? theme.buttonBackgroundHover : theme.buttonBackground)
            : (toggle.hovered || toggle.down ? theme.borderHover : theme.border)
        border.width: 1
        Behavior on color { ColorAnimation { duration: 120 } }

        Rectangle {
            width: 16
            height: 16
            x: toggle.checked ? parent.width - width - 3 : 3
            y: 3
            radius: width / 2
            color: toggle.checked ? theme.buttonText : (theme.dark ? "#ffffff" : theme.textSecondary)
            Behavior on x { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
        }
    }

    contentItem: Text {
        text: toggle.text
        font.pixelSize: 12
        color: toggle.enabled ? theme.textSecondary : theme.textMuted
        leftPadding: toggle.indicator.width + toggle.spacing
        wrapMode: Text.WordWrap
        verticalAlignment: Text.AlignVCenter
    }
}
