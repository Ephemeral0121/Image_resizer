from PyQt5 import QtWidgets, QtCore
from PyQt5.QtWidgets import (QApplication, QMainWindow, QPushButton, QListWidget, QFileDialog,
                              QMessageBox, QVBoxLayout, QWidget, QProgressBar, QLabel, QComboBox,
                                QLineEdit, QHBoxLayout, QStatusBar, QButtonGroup, QRadioButton)
from PyQt5.QtWidgets import QCheckBox
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QFont
import sys
import os
import threading
from PIL import Image
import piexif
import subprocess

# Windows 작업 표시줄 지원
try:
    from PyQt5.QtWinExtras import QWinTaskbarButton, QWinTaskbarProgress
except ImportError:
    QWinTaskbarButton = None  # Windows가 아닌 경우 None으로 설정


class DropArea(QWidget):
    def __init__(self, parent=None):
        super(DropArea, self).__init__(parent)
        self.setAcceptDrops(True)
        self.layout = QVBoxLayout(self)
        self.label = QLabel("↓ Drag and Drop Files Here ↓", self)
        self.label.setAlignment(QtCore.Qt.AlignCenter)
        self.label.setFont(QFont('Arial', 14))
        self.label.setStyleSheet("color: #aaa;")
        self.layout.addWidget(self.label)
        self.fileList = QListWidget(self)
        self.fileList.setFont(QFont('Arial', 12))
        self.layout.addWidget(self.fileList)
        self.setStyleSheet("""
            DropArea {
                border: 2px dashed #ccc;
                border-radius: 10px;
                background-color: #fafafa;
            }
            QListWidget {
                border: none;
            }
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

    def resource_path(self, relative_path):
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)
    
    def __init__(self):
        super().__init__()
        self.initUI()
        self.resizeThread = None
        self.updateProgress.connect(self.updateProgressBar)
        self.showCompleteMessage.connect(self.showCompletionMessage)

    def initUI(self):
        self.setWindowTitle('Image Resizer')
        self.setGeometry(100, 100, 800, 600)
        self.center()
        self.setWindowIcon(QIcon(self.resource_path("image_resizer_icon.png")))

        centralWidget = QWidget(self)
        self.setCentralWidget(centralWidget)
        layout = QVBoxLayout(centralWidget)

        self.keepExifCheckbox = QCheckBox("Keep EXIF Data")
        layout.addWidget(self.keepExifCheckbox)

        self.dropArea = DropArea()
        layout.addWidget(self.dropArea)
        layout.setStretchFactor(self.dropArea, 3)  # 드래그 앤 드롭 영역의 비중을 늘립니다.

        self.openButton = QPushButton('Open Files')
        self.openButton.clicked.connect(self.openImages)
        layout.addWidget(self.openButton)

        # Resolution options using radio buttons
        self.resolutionLayout = QHBoxLayout()
        self.resolutionGroup = QButtonGroup(self)
        for ratio in ["1:1", "4:3", "16:9"]:
            radioButton = QRadioButton(ratio)
            self.resolutionGroup.addButton(radioButton)
            self.resolutionLayout.addWidget(radioButton)
            if ratio == "16:9":
                radioButton.setChecked(True)  # Default selection

        # Custom resolution option
        self.customRadioButton = QRadioButton("Custom")  # self 추가
        self.resolutionGroup.addButton(self.customRadioButton)
        self.resolutionLayout.addWidget(self.customRadioButton)
        layout.addLayout(self.resolutionLayout)

        self.customRadioButton.toggled.connect(self.customRatioToggled)  # 여기에 연결

        # Custom resolution inputs
        self.customResolutionWidget = QWidget()  # 이 위젯을 통해 커스텀 입력 필드를 보여주거나 숨깁니다.
        self.customResolutionLayout = QHBoxLayout(self.customResolutionWidget)
        self.widthInput = QLineEdit()
        self.heightInput = QLineEdit()
        self.customResolutionLayout.addWidget(QLabel("Width:"))
        self.customResolutionLayout.addWidget(self.widthInput)
        self.customResolutionLayout.addWidget(QLabel("Height:"))
        self.customResolutionLayout.addWidget(self.heightInput)
        layout.addWidget(self.customResolutionWidget)
        self.customResolutionWidget.setVisible(False)  # 초기 상태에서 숨김


        self.resizeButton = QPushButton('Resize Images')
        self.resizeButton.clicked.connect(self.resizeImages)
        layout.addWidget(self.resizeButton)

        self.progressBar = QProgressBar()
        layout.addWidget(self.progressBar)

        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)

        self.setStyle()

    def setStyle(self):
        self.setStyleSheet("""
            QPushButton {
                background-color: #007AFF; color: white; border-radius: 5px; padding: 10px;
            }
            QPushButton:hover {
                background-color: #357ae8;
            }
            QRadioButton {
                font-size: 18px;
            }
            QLineEdit {
                font-size: 14px; padding: 5px; border: 1px solid #cccccc; border-radius: 5px;
            }
            QProgressBar {
                font-size: 14px; padding: 5px; border-radius: 5px; background-color: #f0f0f0; border: 1px solid #cccccc;
            }
            QProgressBar::chunk {
                background-color: #4285f4; border-radius: 5px;
            }
        """)


    def showEvent(self, event):
        super().showEvent(event)
        # Windows 작업 표시줄 진행 상태 표시
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
        self.dropArea.fileList.clear()
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

    def customRatioToggled(self, checked):
        self.customResolutionWidget.setVisible(checked)  # 커스텀 비율 입력 위젯의 가시성을 변경

    def getRatio(self):
        if self.customRadioButton.isChecked():  # 여기를 수정
            try:
                width = int(self.widthInput.text())
                height = int(self.heightInput.text())
                if width <= 0 or height <= 0:
                    return None
                return width, height
            except ValueError:
                return None
        else:
            selectedButton = self.resolutionGroup.checkedButton()
            if selectedButton:
                ratioText = selectedButton.text()
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
            self.updateProgress.emit(progress)
        self.showCompleteMessage.emit()

    def resizeImage(self, filePath, ratio):
        try:
            with Image.open(filePath) as img:
                original_width, original_height = img.size
                target_width, target_height = ratio

                # 새로운 크기 계산
                new_width, new_height = self.calculateNewSize(original_width, original_height, ratio)

                # 중앙에서 크롭할 위치 계산
                left = (original_width - new_width) // 2
                top = (original_height - new_height) // 2
                right = left + new_width
                bottom = top + new_height

                # 이미지 크롭 및 리사이징
                cropped_img = img.crop((left, top, right, bottom))

                # 리사이징된 이미지 저장
                base, ext = os.path.splitext(filePath)
                resized_file_path = f"{base}_resized{ext}"
                cropped_img.save(resized_file_path)

                # Keep EXIF Data 체크박스가 체크되어 있으면 exiftool을 사용하여 메타데이터 복사
                if self.keepExifCheckbox.isChecked():
                    exiftool_cmd = f'exiftool -TagsFromFile "{filePath}" -all:all -overwrite_original "{resized_file_path}"'
                    subprocess.run(exiftool_cmd, shell=True, check=True)

                return True
        except Exception as e:
            print(f"Error resizing and cropping image with EXIF preservation: {e}")
            return False


    def calculateNewSize(self, width, height, ratio):
        target_width, target_height = ratio
        aspect_ratio = width / height
        target_aspect_ratio = target_width / target_height

        if aspect_ratio > target_aspect_ratio:
            # 원본이 더 넓은 경우
            new_width = int(height * target_aspect_ratio)
            new_height = height
        else:
            # 원본이 더 높은 경우
            new_width = width
            new_height = int(width / target_aspect_ratio)

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
