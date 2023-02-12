#################################################################################
#                SiEPIC Tools - core                                            #
#################################################################################

'''
Classes
 - Net: connectivity between pins. Used for netlist generation and verification
    data generated by class extensions cell.identify_nets()
 - Component: contains information about a layout component (cell with pins)
    data generated by class extensions cell.find_components()
    and will contain pin objects
 - Pin: pin details (direction);
    data generated by class extensions cell.find_pins()

Netlist format
 <component>_<idx> Net1 Net2 ...

Data structure for netlist, and pointers.
 Component -> Pin -> Net
 - Find components, each one finds its pins
 - overlapping pins define nets
 (note that Python variables are actually pointers
 http://scottlobdell.me/2013/08/understanding-python-variables-as-pointers/
 so when we create an object which references another object, we can easily go backwards if need be)

Also functions:

 - WaveguideGUI
 - CalibreGUI
 - MonteCarloGUI

'''


import pya

'''
Net:
 - connection between pins
  - optical nets can only have two pins
  - electrical nets can have multiple pins
 - the pin array points to Pins
'''


class Net:

    def __init__(self, idx=None, _type=None, pins=None):
        self.idx = idx           # net number, index, should be unique, 0, 1, 2, ...
        self.type = _type        # one of PIN_TYPES, defined in SiEPIC._globals.PINTYPES
        # for backwards linking (optional)
        self.pins = pins         # pin array, Pin[]

    def display(self):
        print('- net: %s, pins: %s' % (self.idx,
                                       [[p.pin_name, p.center.to_s(), p.component.component, p.component.instance] for p in self.pins]))

'''
Pin:
This is a class that describes pins on components and waveguides.
A pin consists of:
 - optical pin: a Path with 2 points, with its vector giving the direction
    of how to leave the component
 - electrical pin: a Box
 - a Text label giving its name
 - a type: OPTICAL, I/O, ELECTRICAL
A pin can be associated with:
 - a component
 - a net

Uses:
 - Waveguide snapping to nearest pin (in waveguide_from_path, and path.snap)
    - does not need info about component, net...
 - Component snapping to nearest pin (in snap_component)
    - does not need info about component, net...
 - Netlist extraction
    - needs connectivity: which component & net the pin belongs to

Pin defs:
 - transform: to move the pin
 - display: list the pin

'''


class Pin():

    def __init__(self, path=None, _type=None, box=None, polygon=None, component=None, net=None, pin_name=None):
        from .utils import angle_vector
        from . import _globals
        self.type = _type           # one of PIN_TYPES, defined in SiEPIC._globals.PINTYPES
        if net:                     # Net for netlist generation
            self.net = net            # which net this pin is connected to
        else:
            self.net = _globals.NET_DISCONNECTED
        self.pin_name = pin_name    # label read from the cell layout (PinRec text)
        self.component = component  # which component index this pin belongs to
        self.path = path            # the pin's Path (Optical)
        self.polygon = polygon      # the pin's polygon (Optical IO)
        if path:
            pts = path.get_points()
            if len(pts) == 2:
              self.center = (pts[0] + pts[1]) * 0.5  # center of the pin: a Point
            else:
              print('SiEPIC-Tools: class Pin():__init__: detected invalid Pin')
              self.rotation = 0
              return
            self.rotation = angle_vector(pts[1] - pts[0])  # direction / angle of the optical pin
        else:
            self.rotation = 0
        self.box = box              # the pin's Box (Electrical)
        if box:
            self.center = box.center()  # center of the pin: a Point
        if polygon:
            self.rotation = 0
            self.center = polygon.bbox().center()  # center of the pin: a Point (relative coordinates, within component)

    def transform(self, trans):
        # Transformation of the pin location
        from .utils import angle_vector
        if self.path:
            self.path = self.path.transformed(trans)
            pts = self.path.get_points()
            self.center = (pts[0] + pts[1]) * 0.5
            self.rotation = angle_vector(pts[1] - pts[0])
        if self.polygon:
            self.polygon = self.polygon.transformed(trans)
            self.center = self.polygon.bbox().center()
            self.rotation = 0
        return self

    def display(self):
        p = self
        print("- pin_name %s: component_idx %s, pin_type %s, rotation: %s, net: %s, (%s), path: %s" %
              (p.pin_name, p.component.idx, p.type, p.rotation, p.net.idx, p.center, p.path))
        o = self
#        print("- pin #%s: component_idx %s, pin_name %s, pin_type %s, net: %s, (%s), path: %s" %
#              (o.idx, o.component_idx, o.pin_name, o.type, o.net.idx, o.center, o.path))


def display_pins(pins):
    print("Pins:")
    for o in pins:
        o.display()


'''
Component:
This is a class that describes components (PCells and fixed)
A component consists of:
 - a layout representation
 - additional information

Uses:
 - Netlist extraction
    - needs connectivity: components and how they are connected (net)

Component defs:
 - display: list the component
 - transform: to move the component
 - find_pins

'''


class Component():

    def __init__(self, idx=None, component=None, instance=None, trans=None, library=None, params=None, pins=[], epins=[], nets=[], polygon=None, DevRec_polygon=None, cell=None, basic_name=None, cellName=None):
        self.idx = idx             # component index, should be unique, 0, 1, 2, ...
        self.component = component  # which component (name) this belongs to
        self.instance = instance   # which component (instance) this belongs to  # Needs to fixed to be pya.Instance
          
        # instance's location (.disp.x, y), mirror (.is_mirror), rotation (angle);
        # in a ICplxTrans class
        # http://www.klayout.de/doc-qt4/code/class_ICplxTrans.html
        self.trans = trans
        self.library = library     # compact model library
        self.pins = pins           # an array of all the optical pins, Pin[]
        self.npins = len(pins)     # number of pins
        self.params = params       # Spice parameters
        # The component's DevRec polygon/box outline (absolute coordinates, i.e., transformed)
        self.polygon = polygon
        # The component's DevRec polygon/box outline (relative coordinates, i.e.,
        # inside cell, just like the pins)
        self.DevRec_polygon = DevRec_polygon
        self.center = polygon.bbox().center()  # Point
        self.cell = cell           # component's cell
        self.basic_name = basic_name  # component's basic_name (especially for PCells)
        self.cellName = cellName  # component's Library Cell name
        from .utils import get_technology
        TECHNOLOGY = get_technology()
        self.Dcenter = self.center.to_dtype(TECHNOLOGY['dbu'])

    def display(self):
        from . import _globals
        cc = self
        if type(cc) != type([]):
          cc=[cc]
        for c in cc:
          c.npins = len(c.pins)
          text = ("- basic_name: %s, component: %s-%s / %s; transformation: %s; center position: %s; number of pins: %s; optical pins: %s; electrical pins: %s; optical IO pins: %s; has compact model: %s; params: %s." %
                (c.basic_name, c.component, c.idx, c.instance, c.trans, c.Dcenter, c.npins,
                 [[p.pin_name, p.center.to_s(), p.net.idx]
                  for p in c.pins if p.type == _globals.PIN_TYPES.OPTICAL],
                    [[p.pin_name, p.center.to_s(), p.net.idx]
                     for p in c.pins if p.type == _globals.PIN_TYPES.ELECTRICAL],
                    [[p.pin_name, p.center.to_s(), p.net.idx]
                     for p in c.pins if p.type == _globals.PIN_TYPES.OPTICALIO],
                    c.has_model(), c.params))
          print(text)
        return text

    def params_dict(self):
      from decimal import Decimal
      if not(self.params):
        return {}
      dicta=[s for s in self.params.split(' ')]  
      dictb={}
      for s in dicta:
          # print('params_dict: %s, %s' % (dicta, s))
          if s == '':
            continue
          if '.' not in s.split('=')[1] and 'e' not in s.split('=')[1].lower():
            # integer
            dictb[s.split('=')[0]]=int(s.split('=')[1])
          else:
            string = s.split('=')[1]
            if '[' in string:
                q=s.split('=')[1]
            else:            
                string = string.replace('u','e-6').replace('n','e-9')
                # print (string)
                q=float(Decimal(string)*Decimal('1e6'))  # in microns
            dictb[s.split('=')[0]]=q
      return dictb

    def find_pins(self):
        return self.cell.find_pins_component(self)

    def has_model(self):

        # check if this component has a compact model in the INTC library
        from ._globals import INTC_ELEMENTS
        if self.library and self.component:
            return (self.library.lower().replace('/','::') + "::" + self.component.lower()) in INTC_ELEMENTS
        else:
            from .utils import get_layout_variables
            TECHNOLOGY, lv, ly, cell = get_layout_variables()
            return ("design kits::" + TECHNOLOGY['technology_name'].lower() + "::" + self.component.lower()) in INTC_ELEMENTS
          

    def get_polygons(self, include_pins=True):
        from .utils import get_layout_variables
        TECHNOLOGY, lv, ly, cell = get_layout_variables()

        r = pya.Region()

        s = self.cell.begin_shapes_rec(ly.layer(TECHNOLOGY['Waveguide']))
        while not(s.at_end()):
            if s.shape().is_polygon() or s.shape().is_box() or s.shape().is_path():
                r.insert(s.shape().polygon.transformed(s.itrans()))
            s.next()

        if include_pins:
            s = self.cell.begin_shapes_rec(ly.layer(TECHNOLOGY['PinRec']))
            import math
            from .utils import angle_vector
            while not(s.at_end()):
                if s.shape().is_path():
                    p = s.shape().path.transformed(s.itrans())
                    # extend the pin path by 1 micron for FDTD simulations
                    pts = [pt for pt in p.each_point()]
                    # direction / angle of the optical pin
                    rotation = angle_vector(pts[0] - pts[1]) * math.pi / 180
                    pts[1] = (pts[1] - pya.Point(int(math.cos(rotation) * 1000),
                                                 int(math.sin(rotation) * 1000))).to_p()
                    r.insert(pya.Path(pts, p.width).polygon())
                s.next()

        r.merge()
        polygons = [p for p in r.each_merged()]

        return polygons


class WaveguideGUI():
    # waveguide types are read from WAVEGUIDES.xml in the PDK

    def __init__(self):
        import os

        ui_file = pya.QFile(os.path.join(os.path.dirname(
            os.path.realpath(__file__)), "files", "waveguide_gui.ui"))
        ui_file.open(pya.QIODevice().ReadOnly)
        self.window = pya.QFormBuilder().load(ui_file, pya.Application.instance().main_window())
        ui_file.close

        # Button Bindings
        self.window.findChild('ok').clicked(self.ok)
        self.window.findChild('cancel').clicked(self.close)
        self.window.findChild('adiabatic').toggled(self.enable)
        self.window.findChild('bezier').setEnabled(False)
        self.window.findChild("configuration").currentIndexChanged(self.config_changed)
        self.loaded_technology = ''
        self.clicked = True

    def enable(self, val):
        if self.window.findChild('adiabatic').isChecked():
            self.window.findChild('bezier').setEnabled(True)
        else:
            self.window.findChild('bezier').setEnabled(False)

    def update(self):
        from .utils import get_layout_variables, load_Waveguides_by_Tech
        TECHNOLOGY, lv, ly, cell = get_layout_variables()
        tech_name = TECHNOLOGY['technology_name']
        self.window.findChild("configuration").clear()
        waveguide_types = load_Waveguides_by_Tech(tech_name)
        self.waveguides = waveguide_types
        # print ('SiEPIC.core, Waveguide GUI: tech %s, waveguide_types: %s' % (tech_name, waveguide_types) )
        if 0:
            # keep only simple waveguides (not compound ones)
            waveguide_types_simple = [t for t in waveguide_types if not 'compound_waveguide' in t.keys()]
            self.waveguides = waveguide_types_simple
        try:
            self.options = [waveguide['name'] for waveguide in self.waveguides]
        except:
            raise Exception('No waveguides found for technology=%s. Check that there exists a technology definition file %s.lyt and a WAVEGUIDES.xml file in the PDK folder. \n(Error in SiEPIC.core.WaveguideGUI.update)' % (tech_name, tech_name) )
#            raise Exception("Problem with waveguide configuration. Error in SiEPIC.core.WaveguideGUI.update")
        self.window.findChild("configuration").addItems(self.options)

    def close(self, val):
        self.clicked = False
        self.window.close()

    def ok(self, val):
        self.clicked = True
        self.window.close()

    def config_changed(self, val):
        waveguide_type = self.window.findChild('configuration').currentText
        if not waveguide_type:
            # no waveguide selected in the GUI
            waveguide_type = self.waveguides[0]['name']
        params = [t for t in self.waveguides if t['name'] == waveguide_type]
        if not params:
            raise Exception("Waveguides '%s' not found. \n(Error in SiEPIC.core.WaveguideGUI.update)" % (waveguide_type) )
        params = params[0]
        if 'compound_waveguide' in params.keys():
            # Find the single mode waveguide, and put that in the text fields
            if 'singlemode' in params['compound_waveguide']:
                singlemode = params['compound_waveguide']['singlemode']
                from .utils import get_layout_variables, load_Waveguides_by_Tech
                TECHNOLOGY, lv, ly, cell = get_layout_variables()
                tech_name = TECHNOLOGY['technology_name']
                waveguide_types = load_Waveguides_by_Tech(tech_name)
                waveguide = [t for t in waveguide_types if t['name'] == singlemode][0]
            else:
                raise Exception('error: waveguide type (%s) does not have singlemode defined' % waveguide_type)            
        else:
            # regular waveguide
            waveguide = params
        if waveguide:
            if 'width' in waveguide:
                self.window.findChild('width').text = waveguide['width']
            elif 'wg_width' in waveguide:
                self.window.findChild('width').text = waveguide['wg_width']
            else:
                self.window.findChild('width').text = '0.5'
            if 'radius' in waveguide:
                self.window.findChild('radius').text = waveguide['radius']
            else:
                self.window.findChild('radius').text = '5'
            if waveguide['adiabatic']:
                self.window.findChild('adiabatic').setChecked(True)
                self.window.findChild('bezier').text = str(waveguide['bezier'])
            else:
                self.window.findChild('adiabatic').setChecked(False)
#                self.window.findChild('bezier').text = '0.45'  # 0.45 makes a radial bend
                self.window.findChild('bezier').text = ''
                
# in 0.3.77, made the GUI read-only; returning back to editable in 0.3.79 based on user request
#        self.window.findChild('bezier').setEnabled(False)
#        self.window.findChild('adiabatic').setEnabled(False)
#        self.window.findChild('radius').setEnabled(False)
#        self.window.findChild('width').setEnabled(False)
#        self.window.findChild('bezier').setEnabled(False)


    def get_parameters(self, show):
        from .utils import get_technology
        TECHNOLOGY = get_technology()

        if not self.loaded_technology == TECHNOLOGY['technology_name']:
            self.update()
            self.window.exec_()
        elif show:
            self.window.exec_()

        if not self.clicked:
            self.loaded_technology = ''
            return None

        self.loaded_technology = TECHNOLOGY['technology_name']
        
        bezier = self.window.findChild('bezier').text
        params = {'radius': float(self.window.findChild('radius').text),
                  'width': float(self.window.findChild('width').text),
                  'adiabatic': self.window.findChild('adiabatic').isChecked(),
                  'bezier': 0 if bezier=='' else float(bezier),
                  'wgs': []}

        waveguide_type = self.window.findChild('configuration').currentText
        if not self.window.findChild('configuration').currentText == '':
            waveguide = [wg for wg in self.waveguides if wg['name'] == waveguide_type][0]
            params['waveguide_type'] = self.window.findChild('configuration').currentText

            if 'component' in waveguide.keys():
                for component in waveguide['component']:
                    params['wgs'].append({
                        'layer': component['layer'], 
                        'width': float(component['width']), 
                        'offset': float(component['offset'])})
#                    w = (params['wgs'][-1]['width'] / 2 + params['wgs'][-1]['offset']) * 2
                    # parameters: CML and model to support multiple WG models
                    if 'CML' in waveguide:
                        params['CML'] = waveguide['CML']
                    else:
                        params['CML'] = ''
                    if 'model' in waveguide:
                        params['model'] = waveguide['model']
                    else:
                        params['model'] = ''
            return params
        else:
            return None


class MonteCarloGUI():

    def __init__(self):
        import os

        ui_file = pya.QFile(os.path.join(os.path.dirname(
            os.path.realpath(__file__)), "files", "monte_carlo_gui.ui"))
        ui_file.open(pya.QIODevice().ReadOnly)
        self.window = pya.QFormBuilder().load(ui_file, pya.Application.instance().main_window())
        ui_file.close

        self.window.findChild('run').clicked(self.ok)
        self.window.findChild('cancel').clicked(self.close)
        self.window.findChild("technology").currentIndexChanged(self.tech_changed)
        self.window.findChild('num_wafers').minimum = 1
        self.window.findChild('num_dies').minimum = 1
        self.loaded_technology = ''
        self.clicked = True

    def close(self, val):
        self.clicked = False
        self.window.close()

    def ok(self, val):
        self.clicked = True
        self.window.close()

    def update(self):
        from .utils import get_layout_variables, load_Monte_Carlo
        TECHNOLOGY, lv, ly, cell = get_layout_variables()
        self.montecarlos = load_Monte_Carlo()
        self.technologies = [mc['name'] for mc in self.montecarlos]
        self.window.findChild("technology").clear()
        self.window.findChild("technology").addItems(self.technologies)
        self.window.findChild('technology').setCurrentIndex(0)

    def tech_changed(self, val):
        options = [t for t in self.montecarlos if t['name'] ==
                   self.window.findChild('technology').currentText]
        if options:
            technology = options[0]
            self.window.findChild('std_dev').text = technology['wafer']['width']['std_dev']
            self.window.findChild('corr_len').text = technology['wafer']['width']['corr_length']
            self.window.findChild('std_dev_2').text = technology['wafer']['height']['std_dev']
            self.window.findChild('corr_len_2').text = technology['wafer']['height']['corr_length']
            self.window.findChild('std_dev_3').text = technology[
                'wafer_to_wafer']['width']['std_dev']
            self.window.findChild('std_dev_4').text = technology[
                'wafer_to_wafer']['thickness']['std_dev']

    def get_parameters(self):
        from .utils import get_technology
        TECHNOLOGY = get_technology()

        if not self.loaded_technology == TECHNOLOGY['technology_name']:
            self.update()
            self.loaded_technology = TECHNOLOGY['technology_name']

        self.window.exec_()
        if not self.clicked:
            return None

        return {
            'num_wafers': self.window.findChild('num_wafers').value,
            'num_dies': self.window.findChild('num_dies').value,
            'technology': self.window.findChild('technology').currentText,
            'histograms': {
                'fsr': self.window.findChild('fsr').isChecked(),
                'gain': self.window.findChild('gain').isChecked(),
                'wavelength': self.window.findChild('wavelength').isChecked()
            },
            'waf_var': {
                'width': {
                    'std_dev': float(self.window.findChild('std_dev').text),
                    'corr_len': float(self.window.findChild('corr_len').text)
                },
                'height': {
                    'std_dev': float(self.window.findChild('std_dev_2').text),
                    'corr_len': float(self.window.findChild('corr_len_2').text)
                }
            },
            'waf_to_waf_var': {
                'width': {
                    'std_dev': float(self.window.findChild('std_dev_3').text)
                },
                'thickness': {
                    'std_dev': float(self.window.findChild('std_dev_4').text)
                }
            }
        }
