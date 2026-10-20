import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

AbstractButton {
    id: control
    property string label: ""
    property string symbol: "display"
    property bool selected: false
    implicitHeight: 88
    background: Rectangle {
        radius: theme.controlRadius
        color: control.hovered && !control.selected ? theme.surfaceAlt : "transparent"
    }
    contentItem: ColumnLayout {
        spacing: 8
        LineIcon { symbol: control.symbol; tint: control.selected ? theme.buttonText : (theme.iconTint); Layout.alignment: Qt.AlignHCenter; Layout.preferredWidth: 28; Layout.preferredHeight: 28 }
        Text { text: control.label; color: control.selected ? theme.buttonText : theme.textPrimary; font.pixelSize: 12; Layout.alignment: Qt.AlignHCenter }
    }
}
