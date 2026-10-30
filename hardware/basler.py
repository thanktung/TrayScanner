"""
hardware/basler.py — Basler camera drivers (single + dual/stereo).
"""

import cv2
import os
from datetime import datetime
from pypylon import pylon


class BaslerCamera:
    def __init__(self, save_folder="raw_images"):
        self.cam = None
        self.converter = None
        self.save_folder = save_folder

        os.makedirs(self.save_folder, exist_ok=True)

    # -----------------------------
    # CONNECT CAMERA
    # -----------------------------
    def connect(self):
        try:
            self.cam = pylon.InstantCamera(
                pylon.TlFactory.GetInstance().CreateFirstDevice()
            )
            self.cam.Open()

            # Image converter
            self.converter = pylon.ImageFormatConverter()
            self.converter.OutputPixelFormat = pylon.PixelType_BGR8packed
            self.converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned

            print("[Basler] Connected")
            return True
        except Exception as e:
            print("[Basler] Connect Error:", e)
            self.cam = None
            return False

    # -----------------------------
    # DISCONNECT CAMERA
    # -----------------------------
    def disconnect(self):
        try:
            if self.cam:
                self.cam.Close()
                print("[Basler] Disconnected")
            self.cam = None
        except Exception as e:
            print("[Basler] Disconnect Error:", e)

    # -----------------------------
    # CAPTURE ONE FRAME (RETURN IMAGE)
    # -----------------------------
    def grab(self, timeout=3000):
        if self.cam is None:
            print("[Basler] Error: Camera not connected.")
            return None

        try:
            self.cam.StartGrabbingMax(1)
            grab = self.cam.RetrieveResult(timeout, pylon.TimeoutHandling_ThrowException)

            if grab.GrabSucceeded():
                img = self.converter.Convert(grab).GetArray()
                grab.Release()
                return img

            grab.Release()
            return None

        except Exception as e:
            print("[Basler] Grab Error:", e)
            return None

    # -----------------------------
    # CAPTURE + SAVE TO FOLDER
    # -----------------------------
    def capture_and_save(self, ext=".png"):
        img = self.grab()
        if img is None:
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(self.save_folder, f"{timestamp}{ext}")

        try:
            cv2.imwrite(filename, img)
            return filename
        except Exception as e:
            print("[Basler] Save Error:", e)
            return None


class DualBaslerCamera:
    def __init__(self, save_folder="raw_images", concat_mode="h"):
        """
        concat_mode: "h" = ghép ngang, "v" = ghép dọc
        """
        self.cams = []
        self.converter = None
        self.save_folder = save_folder
        self.concat_mode = concat_mode

        os.makedirs(self.save_folder, exist_ok=True)

    # -----------------------------
    # CONNECT 2 CAMERAS
    # -----------------------------
    def connect(self):
        try:
            tl_factory = pylon.TlFactory.GetInstance()
            devices = tl_factory.EnumerateDevices()

            if len(devices) < 2:
                raise RuntimeError("Không đủ 2 camera Basler")

            self.cams = [
                pylon.InstantCamera(tl_factory.CreateDevice(devices[0])),
                pylon.InstantCamera(tl_factory.CreateDevice(devices[1]))
            ]

            for cam in self.cams:
                cam.Open()

            self.converter = pylon.ImageFormatConverter()
            self.converter.OutputPixelFormat = pylon.PixelType_BGR8packed
            self.converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned

            print("[DualBasler] Connected 2 cameras")
            return True

        except Exception as e:
            print("[DualBasler] Connect Error:", e)
            self.cams = []
            return False

    # -----------------------------
    # DISCONNECT
    # -----------------------------
    def disconnect(self):
        for cam in self.cams:
            if cam.IsOpen():
                cam.Close()
        self.cams = []
        print("[DualBasler] Disconnected")

    def grab(self, timeout=3000):
        if len(self.cams) != 2:
            print("[DualBasler] Camera not connected")
            return None

        try:
            # start grab
            for cam in self.cams:
                cam.StartGrabbingMax(1)

            imgs = []
            for cam in self.cams:
                grab = cam.RetrieveResult(timeout, pylon.TimeoutHandling_ThrowException)
                if not grab.GrabSucceeded():
                    grab.Release()
                    return None

                img = self.converter.Convert(grab).GetArray()
                grab.Release()
                imgs.append(img)

            if len(imgs) != 2:
                return None

            img1, img2 = imgs
            img2 = cv2.rotate(img2, cv2.ROTATE_180)  # camera 2 lắp ngược

            # ===== ĐẢM BẢO CÙNG SIZE TRƯỚC KHI GHÉP =====
            if self.concat_mode == "h":
                h = min(img1.shape[0], img2.shape[0])
                img1 = cv2.resize(img1, (img1.shape[1], h))
                img2 = cv2.resize(img2, (img2.shape[1], h))
                merged = cv2.hconcat([img1, img2])
            else:
                w = min(img1.shape[1], img2.shape[1])
                img1 = cv2.resize(img1, (w, img1.shape[0]))
                img2 = cv2.resize(img2, (w, img2.shape[0]))
                merged = cv2.vconcat([img1, img2])

            # ===== CHECK CUỐI =====
            if not hasattr(merged, "shape"):
                print("[DualBasler] Merge failed")
                return None

            return merged

        except Exception as e:
            print("[DualBasler] Grab Error:", e)
            return None

    # -----------------------------
    # CAPTURE + MERGE + SAVE
    # NOTE: kept for API symmetry with BaslerCamera, but unused by the GUI
    # (which calls grab() directly, since it already returns the merged
    # image). Fixed a pre-existing bug here: grab() returns ONE merged
    # image, not an (img1, img2) tuple, so unpacking it directly would
    # always raise. Re-grab explicitly instead.
    # -----------------------------
    def capture_and_save(self, ext=".png"):
        merged = self.grab()
        if merged is None:
            return None

        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(self.save_folder, f"{timestamp}{ext}")

            cv2.imwrite(filename, merged)
            return filename

        except Exception as e:
            print("[DualBasler] Save Error:", e)
            return None
