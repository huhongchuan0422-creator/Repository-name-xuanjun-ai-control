"""Pixel-rotation/coordinate/schema contracts with synthetic arrays and fake OCR.

These do not claim original-model inference or real-document accuracy.
"""
import copy
import hashlib
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import numpy as np
from scripts import community_license_inference as wrapper
from scripts.community_license_layout import normalize_layout
from scripts.community_identity_layout import extract_identity_fields


def raw_front():
    return {'txts':['姓名','合成甲','住址','合成地址','公民身份号码','111111111111111111'],
        'scores':[.99]*6,
        'boxes':[[[x,y],[x+w,y],[x+w,y+10],[x,y+10]] for x,y,w in
            [(0,0,20),(25,0,30),(0,30,20),(25,30,50),(0,60,40),(45,60,120)]]}


class OrientationTests(unittest.TestCase):
    def test_inverse_pixel_coordinates_all_quarter_turns(self):
        width,height=31,19
        original=[[2,3],[11,3],[11,8],[2,8]]
        for turn in range(4):
            points=[]
            for x,y in original:
                for k in range(turn):
                    w=width if k%2==0 else height
                    x,y=y,w-1-x
                points.append([x,y])
            self.assertEqual(wrapper._original_box(points,turn,width,height),original)

    def test_nested_source_boxes_are_not_rotated_twice(self):
        result=extract_identity_fields(normalize_layout(raw_front()),coordinate_turns=(0,))
        original=copy.deepcopy(result['fields']['id_name']['source_boxes'])
        mapped=wrapper._map_sources(result,1,200,100)
        f=mapped['fields']['id_name']
        expected=[dict(source_index=s['source_index'],box=wrapper._original_box(s['box'],1,200,100)) for s in original]
        self.assertEqual(f['source_boxes'],expected)
        self.assertEqual(f['candidates'][0]['source_boxes'],expected)

    def test_ambiguous_directions_preserve_conflicting_values(self):
        result=extract_identity_fields(normalize_layout(raw_front()),coordinate_turns=(0,))
        other=copy.deepcopy(result);other['fields']['id_name']['value']='合成乙'
        other['fields']['id_name']['candidates'][0]['value']='合成乙'
        runs=[{'turn':0,'rank':(3,3,3),'evidence':{},'result':result},
              {'turn':2,'rank':(3,3,3),'evidence':{},'result':other}]
        out=wrapper._choose_orientation(runs,'id_front',200,100)
        self.assertIsNone(out['correction_counterclockwise_degrees'])
        self.assertTrue(out['orientation']['ambiguous'])
        self.assertEqual(out['fields']['id_name']['value'],'')
        self.assertEqual(out['fields']['registered_address']['source_boxes'],[])
        self.assertIsNone(out['fields']['registered_address']['correction_counterclockwise_degrees'])
        self.assertEqual({c['value'] for c in out['fields']['id_name']['candidates']},{'合成甲','合成乙'})

    def test_confidence_is_not_a_hidden_orientation_cutoff(self):
        result=extract_identity_fields(normalize_layout(raw_front()),coordinate_turns=(0,))
        rank,_=wrapper._orientation_evidence(normalize_layout(raw_front()),result,'id_front')
        low=copy.deepcopy(result)
        for field in low['fields'].values():field['confidence']=.001
        self.assertEqual(rank,wrapper._orientation_evidence(normalize_layout(raw_front()),low,'id_front')[0])

    def test_wrapper_rotates_actual_pixels_four_calls_one_engine(self):
        upright=np.arange(80*180*3,dtype=np.uint8).reshape(80,180,3)
        for input_turn in range(4):
            with self.subTest(input_turn=input_turn), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);pins={}
                for name in wrapper.UPSTREAM_FILES:
                    data=name.encode();(root/name).write_bytes(data);pins[name]=hashlib.sha256(data).hexdigest()
                core=types.SimpleNamespace(__file__=str(root/'ocr_core.py'),_verified_model_paths=lambda:{'det':'d','cls':'c','rec':'r'})
                package=types.ModuleType('services');engine_package=types.ModuleType('services.ocr_engine');engine_package.ocr_core=core
                current=np.ascontiguousarray(np.rot90(upright,input_turn)); calls=[];created=[]
                class Engine:
                    def __init__(self,params):created.append(params)
                    def __call__(self,pixels):
                        calls.append(pixels.copy())
                        return raw_front() if np.array_equal(pixels,upright) else {'txts':None,'scores':None,'boxes':None}
                cv2=types.SimpleNamespace(IMREAD_COLOR=1,imdecode=lambda data,flag:current.copy())
                modules={'services':package,'services.ocr_engine':engine_package,'rapidocr':types.SimpleNamespace(RapidOCR=Engine),'cv2':cv2}
                with patch.dict(sys.modules,modules),patch.object(wrapper,'UPSTREAM_FILES',pins):
                    out=wrapper.run_license_layout_ocr(b'\x89PNG\r\n\x1a\nSYNTHETIC','id_front')
                self.assertEqual(len(created),1);self.assertEqual(len(calls),4)
                self.assertEqual(out['orientation']['inference_calls'],4)
                self.assertEqual(out['correction_counterclockwise_degrees'],(-input_turn*90)%360)
                self.assertTrue(out['extraction_after_pixel_rotation'])
                self.assertEqual(out['fields']['id_name']['value'],'合成甲')
                for turn,pixels in enumerate(calls):self.assertTrue(np.array_equal(pixels,np.rot90(current,turn)))
                original_quad=raw_front()['boxes'][1]
                self.assertEqual(out['fields']['id_name']['value_boxes'],[wrapper._original_box(original_quad,(-input_turn)%4,current.shape[1],current.shape[0])])

    def test_empty_pages_do_not_establish_orientation(self):
        runs=[{'turn':i,'rank':(0,0,0),'evidence':{},'result':{'fields':{}}} for i in range(4)]
        result=wrapper._choose_orientation(runs,'id_front',100,200)
        self.assertTrue(result['orientation']['ambiguous']);self.assertIsNone(result['correction_counterclockwise_degrees'])

if __name__=='__main__':unittest.main()
