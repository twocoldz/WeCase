import os
from time import sleep
import urllib.request
from urllib.error import URLError, ContentTooShortError
from http.client import BadStatusLine
from PyQt4 import QtCore, QtGui
from WImageLabel import WImageLabel
from const import cache_path as down_path
from const import icon
from WeHack import async
from WObjectCache import WObjectCache
import logging


class WAsyncLabel(WImageLabel):

    clicked = QtCore.pyqtSignal(int)

    def __init__(self, parent=None):
        super(WAsyncLabel, self).__init__(parent)
        self._url = ""
        self._image = None

        self.fetcher = WAsyncFetcher(self)
        self.fetcher.fetched.connect(self._setPixmap)

        busyIconPixmap = WObjectCache().open(QtGui.QPixmap, icon("busy.gif"))
        self.minimumImageHeight = busyIconPixmap.height()
        self.minimumImageWidth = busyIconPixmap.width()

        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.contextMenu)

    def url(self):
        return self._url

    def setBusy(self, busy):
        if busy:
            # XXX: # Issue #74.
            # What's wrong with the busyMovie()? To save the memory,
            # We use a single busyMovie() in the whole program.
            # If the image downloaded here, we'll stop the movie and the
            # busyIcon will disappear. But it may start from somewhere else.
            # The the busyIcon appear again unexpectedly.
            # The quick fix is disconnecting the signal/slot connection
            # when we stop the movie.
            self.animation = WObjectCache().open(QtGui.QMovie, icon("busy.gif"))
            self.animation.start()
            self.animation.frameChanged.connect(self.drawBusyIcon)
        else:
            self.clearBusyIcon()

    @QtCore.pyqtSlot()
    def drawBusyIcon(self):
        image = QtGui.QPixmap(self._image)
        icon = self.animation.currentPixmap()

        height = (image.height() - icon.height()) / 2
        width = (image.width() - icon.width()) / 2
        painter = QtGui.QPainter(image)
        painter.drawPixmap(width, height, icon)
        painter.end()
        super(WAsyncLabel, self).setPixmap(image)

    def clearBusyIcon(self):
        self.animation.stop()
        self.animation.frameChanged.disconnect(self.drawBusyIcon)
        super(WAsyncLabel, self).setPixmap(self._image)

    def _setPixmap(self, path):
        _image = QtGui.QPixmap(path)
        minimalHeight = self.minimumImageHeight
        minimalWidth = self.minimumImageWidth

        if _image.height() < minimalHeight or _image.width() < minimalWidth:
            if _image.height() > minimalHeight:
                height = _image.height()
            else:
                height = minimalHeight

            if _image.width() > minimalWidth:
                width = _image.width()
            else:
                width = minimalWidth

            image = QtGui.QPixmap(width, height)
            painter = QtGui.QPainter(image)
            path = QtGui.QPainterPath()
            path.addRect(0, 0, width, height)
            painter.fillPath(path, QtGui.QBrush(QtCore.Qt.gray))
            painter.drawPixmap((width - _image.width()) / 2,
                               (height - _image.height()) / 2,
                               _image)
            painter.end()
        else:
            image = _image

        self._image = image
        super(WAsyncLabel, self).setPixmap(image)

    def setPixmap(self, url):
        super(WAsyncLabel, self).setMovie(
            WObjectCache().open(QtGui.QMovie, icon("busy.gif"))
        )
        self.start()
        if not ("http" in url):
            self._setPixmap(url)
            return
        self._url = url
        self._fetch()

    def _fetch(self):
        self.fetcher.fetch(self._url)

    def mouseReleaseEvent(self, e):
        if e.button() == QtCore.Qt.LeftButton and self._image:
            self.clicked.emit(QtCore.Qt.LeftButton)
        elif e.button() == QtCore.Qt.MiddleButton and self._image:
            self.clicked.emit(QtCore.Qt.MiddleButton)

    def contextMenu(self, pos):
        if not self._image:
            return
        saveAction = QtGui.QAction(self)
        saveAction.setText(self.tr("&Save"))
        saveAction.triggered.connect(self.save)
        menu = QtGui.QMenu()
        menu.addAction(saveAction)
        menu.exec(self.mapToGlobal(pos))

    def save(self):
        file = QtGui.QFileDialog.getOpenFileName(self,
                                                 self.tr("Choose a path"))
        self._image.save(file)


class WAsyncFetcher(QtCore.QObject):

    fetched = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        super(WAsyncFetcher, self).__init__(parent)

    @staticmethod
    def _formattedFilename(url):
        return "%s_%s" % (url.split('/')[-2],
                          url.split('/')[-1])

    def down(self, url, filename=""):
        if not filename:
            filename = self._formattedFilename(url)

        def delete_tmp():
            try:
                os.remove(down_path + filename + ".down")
                return True
            except OSError:
                return False

        def download():
            while 1:
                try:
                    urllib.request.urlretrieve(url, down_path + filename + ".down")
                    os.rename(down_path + filename + ".down",
                              down_path + filename)
                    return
                except (BadStatusLine, URLError, ContentTooShortError):
                    continue
                except OSError:
                    return

        while 1:
            if os.path.exists(down_path + filename):
                delete_tmp()
                try:
                    self.fetched.emit(down_path + filename)
                except TypeError:
                    # Garbage Collected
                    pass
                return down_path + filename
            elif os.path.exists(down_path + filename + ".down"):
                sleep(0.5)
                continue
            else:
                try:
                    download()
                except Exception as e:
                    # Issue #72, log it for further research.
                    logging.error(str(e))
                    return

    @async
    def fetch(self, url, filename=""):
        self.down(url, filename)
