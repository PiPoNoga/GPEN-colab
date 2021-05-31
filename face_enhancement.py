'''
@paper: GAN Prior Embedded Network for Blind Face Restoration in the Wild (CVPR2021)
@author: yangxy (yangtao9009@gmail.com)
'''
import os
import cv2
import glob
import time
import numpy as np
from PIL import Image
import __init_paths
from retinaface.retinaface_detection import RetinaFaceDetection
from face_model.face_gan import FaceGAN
from align_faces import warp_and_crop_face, get_reference_facial_points
from skimage import transform as tf

class FaceEnhancement(object):
    def __init__(self, base_dir='./', size=1024, model=None, channel_multiplier=2):
        self.facedetector = RetinaFaceDetection(base_dir)
        self.facegan = FaceGAN(base_dir, size, model, channel_multiplier)
        self.size = size
        self.threshold = 0.9

        self.mask = np.zeros((512, 512), np.float32)
        cv2.rectangle(self.mask, (26, 26), (486, 486), (1, 1, 1), -1, cv2.LINE_AA)
        self.mask = cv2.GaussianBlur(self.mask, (101, 101), 11)
        self.mask = cv2.GaussianBlur(self.mask, (101, 101), 11)

        self.kernel = np.array((
                [0.0625, 0.125, 0.0625],
                [0.125, 0.25, 0.125],
                [0.0625, 0.125, 0.0625]), dtype="float32")

        # get the reference 5 landmarks position in the crop settings
        default_square = True
        inner_padding_factor = 0.25
        outer_padding = (0, 0)
        self.reference_5pts = get_reference_facial_points(
                (self.size, self.size), inner_padding_factor, outer_padding, default_square)

    def process(self, img):
        if len(img.shape)==2 or img.shape[2]==1:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        if img.shape[2]==4:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

        facebs, landms = self.facedetector.detect(img)
        
        orig_faces, enhanced_faces = [], []
        height, width = img.shape[:2]
        full_mask = np.zeros((height, width), dtype=np.float32)
        full_img = np.zeros(img.shape, dtype=np.uint8)

        for i, (faceb, facial5points) in enumerate(zip(facebs, landms)):
            if faceb[4]<self.threshold: continue
            fh, fw = (faceb[3]-faceb[1]), (faceb[2]-faceb[0])

            facial5points = np.reshape(facial5points, (2, 5))

            of, tfm_inv = warp_and_crop_face(img, facial5points, reference_pts=self.reference_5pts, crop_size=(self.size, self.size))
            
            # enhance face
            ef = self.facegan.process(of)
            
            orig_faces.append(of)
            enhanced_faces.append(ef)
            
            tmp_mask = self.mask
            tmp_mask = cv2.resize(tmp_mask, ef.shape[:2])
            tmp_mask = cv2.warpAffine(tmp_mask, tfm_inv, (width, height), flags=3)

            if min(fh, fw)<100: # gaussian filter for small face
                ef = cv2.filter2D(ef, -1, self.kernel)
            
            tmp_img = cv2.warpAffine(ef, tfm_inv, (width, height), flags=3)

            mask = tmp_mask - full_mask
            full_mask[np.where(mask>0)] = tmp_mask[np.where(mask>0)]
            full_img[np.where(mask>0)] = tmp_img[np.where(mask>0)]

        full_mask = full_mask[:, :, np.newaxis]
        img = cv2.convertScaleAbs(img*(1-full_mask) + full_img*full_mask)

        return img, orig_faces, enhanced_faces
        

if __name__=='__main__':
    model = {'name':'GPEN-512', 'size':512}
    
    indir = 'examples/imgs'
    outdir = 'examples/outs'
    os.makedirs(outdir, exist_ok=True)

    faceenhance = FaceEnhancement(size=model['size'], model=model['name'], channel_multiplier=2)

    files = sorted(glob.glob(os.path.join(indir, '*.*g')))
    for n, filename in enumerate(files[:]):
        file = os.path.basename(filename)
        
        im = cv2.imread(filename)
        if not isinstance(im, np.ndarray): print(filename, 'error'); continue
        im = cv2.resize(im, (0,0), fx=2, fy=2)

        img, orig_faces, enhanced_faces = faceenhance.process(im)
        
        cv2.imwrite(os.path.join(outdir, ''.join(file.split('.')[:-1])+'_COMP.jpg'), np.hstack((im, img)))
        cv2.imwrite(os.path.join(outdir, ''.join(file.split('.')[:-1])+'_GPEN.jpg'), img)
        
        for n, (ef, of) in enumerate(zip(enhanced_faces, orig_faces)):
            of = cv2.resize(of, ef.shape[:2])
            cv2.imwrite(os.path.join(outdir, ''.join(file.split('.')[:-1])+'_face%02d'%n+'.jpg'), np.hstack((of, ef)))
        
        if n%10==0: print(n, file)
        