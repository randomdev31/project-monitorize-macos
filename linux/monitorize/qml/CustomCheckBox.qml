import QtQuick
import QtQuick.Controls

CheckBox {
    id: chk
    hoverEnabled: true
    property bool keepCheckedBlue: false
    property bool expandableLabel: false
    signal labelClicked()

    indicator: Rectangle {
        implicitWidth: 16
        implicitHeight: 16
        x: chk.leftPadding
        y: parent.height / 2 - height / 2
        radius: 4
        color: chk.keepCheckedBlue && chk.checked ? theme.buttonBackground : !chk.enabled ? theme.surfaceAlt : chk.checked
            ? (chk.hovered || chk.down ? theme.buttonBackgroundHover : theme.buttonBackground)
            : (chk.hovered || chk.down ? theme.surfaceAlt : theme.surface)
        border.color: chk.keepCheckedBlue && chk.checked ? theme.buttonBackground : !chk.enabled ? theme.border : chk.checked
            ? (chk.hovered || chk.down ? theme.buttonBackgroundHover : theme.buttonBackground)
            : (chk.hovered || chk.down ? theme.borderHover : theme.border)
        border.width: 1

        Text {
            anchors.centerIn: parent
            text: "✓"
            color: theme.buttonText
            font.pixelSize: 11
            font.weight: Font.Bold
            visible: chk.checked
        }
    }
    contentItem: Text {
        text: chk.text
        font.pixelSize: 12
        color: chk.hovered ? theme.textSecondary : theme.textMuted
        leftPadding: chk.indicator.width + chk.spacing
        wrapMode: Text.WordWrap
        verticalAlignment: Text.AlignVCenter
    }
    // Pointer clicks toggle only inside the visible square. Keyboard activation
    // remains handled by CheckBox for accessibility.
    MouseArea {
        anchors.fill: parent
        onPressed: function(mouse) {
            let box = chk.indicator
            if (mouse.x >= box.x && mouse.x <= box.x + box.width &&
                mouse.y >= box.y && mouse.y <= box.y + box.height)
                mouse.accepted = false
        }
        onClicked: function(mouse) {
            if (chk.expandableLabel && mouse.x >= chk.contentItem.x + chk.contentItem.leftPadding)
                chk.labelClicked()
        }
    }

}
