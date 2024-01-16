from PyQt5 import QtWidgets, QtCore
from PyQt5.QtWidgets import (QApplication, QMainWindow, QPushButton, QListWidget, QFileDialog, QMessageBox, QVBoxLayout, QWidget, QProgressBar, QLabel, QComboBox, QLineEdit, QHBoxLayout, QStatusBar)
from PyQt5.QtCore import Qt
from PIL import Image
import sys
import os
import threading

# Windows 작업 표시줄
try:
    from PyQt5.QtWinExtras import QWinTaskbarButton, QWinTaskbarProgress
except ImportError:
    QWinTaskbarButton = None  # Windows가 아닌 경우 None으로 설정

class DropArea(QWidget):
    def __init__(self, parent=None):
        super(DropArea, self).__init__(parent)
        self.setAcceptDrops(True)
        self.layout = QVBoxLayout(self)
        self.label = QLabel("Drag and Drop Files Here", self)
        self.label.setAlignment(QtCore.Qt.AlignCenter)
        self.label.setStyleSheet("color: #aaa; font-style: italic;")
        self.layout.addWidget(self.label)
        self.fileList = QListWidget(self)
        self.layout.addWidget(self.fileList)
        self.setStyleSheet("""
            border: 2px dashed #aaa;
            border-radius: 5px;
            background-color: #f0f0f0;
        """)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.fileList.clear()  # Clear the existing list before adding new files
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.fileList.addItem(url.toLocalFile())
        self.label.hide()

class ImageResizer(QMainWindow):
    updateProgress = QtCore.pyqtSignal(int)
    showCompleteMessage = QtCore.pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.initUI()
        self.resizeThread = None
        self.updateProgress.connect(self.updateProgressBar)
        self.showCompleteMessage.connect(self.showCompletionMessage)

    def initUI(self):
        self.setWindowTitle('Image Resizer')
        self.setGeometry(100, 100, 600, 550)
        self.center()

        centralWidget = QWidget(self)
        self.setCentralWidget(centralWidget)
        layout = QVBoxLayout(centralWidget)

        self.dropArea = DropArea()
        layout.addWidget(self.dropArea)

        self.openButton = QPushButton('Open Files')
        self.openButton.clicked.connect(self.openImages)
        layout.addWidget(self.openButton)

        self.ratioComboBox = QComboBox(self)
        self.ratioComboBox.addItems(["1:1", "4:3", "16:9", "Custom"])
        layout.addWidget(self.ratioComboBox)

        self.customRatioWidget = QWidget(self)
        customLayout = QHBoxLayout(self.customRatioWidget)
        self.widthInput = QLineEdit(self)
        self.heightInput = QLineEdit(self)
        customLayout.addWidget(QLabel("Width:"))
        customLayout.addWidget(self.widthInput)
        customLayout.addWidget(QLabel("Height:"))
        customLayout.addWidget(self.heightInput)
        layout.addWidget(self.customRatioWidget)
        self.customRatioWidget.hide()

        self.ratioComboBox.currentIndexChanged.connect(self.ratioChanged)

        self.resizeButton = QPushButton('Resize Images')
        self.resizeButton.clicked.connect(self.resizeImages)
        layout.addWidget(self.resizeButton)

        self.progressBar = QProgressBar(self)
        layout.addWidget(self.progressBar)

        self.statusBar = QStatusBar(self)
        self.setStatusBar(self.statusBar)

        self.setStyle()

    def setStyle(self):
        self.openButton.setStyleSheet("font-size: 16px; padding: 10px; background-color: #4285f4; color: white; border-radius: 5px;")
        self.resizeButton.setStyleSheet("font-size: 16px; padding: 10px; background-color: #34a853; color: white; border-radius: 5px;")
        self.progressBar.setStyleSheet("font-size: 16px; height: 20px; border-radius: 5px;")
        self.customRatioWidget.setStyleSheet("font-size: 14px;")
    
    def showEvent(self, event):
        super().showEvent(event)
        if QWinTaskbarButton:
            self.taskbarButton = QWinTaskbarButton(self)
            self.taskbarButton.setWindow(self.windowHandle())
            self.taskbarProgress = self.taskbarButton.progress()
            self.taskbarProgress.show()

    def center(self):
        qr = self.frameGeometry()
        cp = QtWidgets.QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def openImages(self):
        self.dropArea.fileList.clear()  # Clear the existing list
        filePaths, _ = QFileDialog.getOpenFileNames(self, "Open Images", "", "Image files (*.jpg *.jpeg *.png)")
        for filePath in filePaths:
            self.dropArea.fileList.addItem(filePath)
        if len(filePaths) > 0:
            self.dropArea.label.hide()

    def ratioChanged(self, index):
        if self.ratioComboBox.currentText() == "Custom":
            self.customRatioWidget.show()
        else:
            self.customRatioWidget.hide()

    def resizeImages(self):
        if not self.dropArea.fileList.count():
            QMessageBox.warning(self, 'Warning', 'No images to resize.')
            return

        ratio = self.getRatio()
        if ratio is None:
            QMessageBox.warning(self, 'Error', 'Invalid custom ratio.')
            return

        if not self.resizeThread or not self.resizeThread.is_alive():
            self.resizeThread = threading.Thread(target=self.performResizing, args=(ratio,))
            self.resizeThread.start()

    def getRatio(self):
        ratioText = self.ratioComboBox.currentText()
        if ratioText == "Custom":
            try:
                width = int(self.widthInput.text())
                height = int(self.heightInput.text())
                if width <= 0 or height <= 0:
                    return None
                return width, height
            except ValueError:
                return None
        else:
            width, height = map(int, ratioText.split(':'))
            return width, height

    def performResizing(self, ratio):
        total_files = self.dropArea.fileList.count()
        for index in range(total_files):
            filePath = self.dropArea.fileList.item(index).text()
            if not self.resizeImage(filePath, ratio):
                self.statusBar().showMessage("Image size too small for selected ratio.", 5000)
                continue
            progress = int((index + 1) / total_files * 100)
            self.updateProgress.emit(progress)  # Update progress bar in main thread
        self.showCompleteMessage.emit()

    def resizeImage(self, filePath, ratio):
        with Image.open(filePath) as img:
            width, height = img.size
            new_width, new_height = self.calculateNewSize(width, height, ratio)

            if new_width > width or new_height > height:
                return False

            left = (width - new_width) // 2
            top = (height - new_height) // 2
            right = (width + new_width) // 2
            bottom = (height + new_height) // 2

            cropped_img = img.crop((left, top, right, bottom))
            base, ext = os.path.splitext(filePath)
            new_file_path= f"{base}_resized{ext}"
            cropped_img.save(new_file_path)
            return True
        
    def calculateNewSize(self, width, height, ratio):
        target_width, target_height = ratio
        new_width = width
        new_height = int(width * target_height / target_width)
        if new_height > height:
            new_height = height
            new_width = int(height * target_width / target_height)
        return new_width, new_height

    @QtCore.pyqtSlot(int)
    def updateProgressBar(self, value):
        self.progressBar.setValue(value)
        if self.taskbarProgress:
            self.taskbarProgress.setValue(value)
            if value == 100:
                self.taskbarProgress.hide()

    @QtCore.pyqtSlot()
    def showCompletionMessage(self):
        self.statusBar.showMessage('All images have been resized and saved.', 5000)
        if QWinTaskbarButton:
            self.taskbarProgress.hide()

def main():
    app = QApplication(sys.argv)
    ex = ImageResizer()
    ex.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
