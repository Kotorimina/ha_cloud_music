"""
安装html解析库
pip3 install Beautifulsoup4 

安装xml解析库
pip3 install lxml
    
上海公交

sensor:
  - platform: shbus
    name: 748路
    direction: 1
    stop_id: 10
  - platform: shbus
    name: 748路
    direction: 0
    stop_id: 6
    
"""

 
 
import requests
import pickle
import os
import time
import math
import json
from bs4 import BeautifulSoup
import aiohttp
from aiohttp import web
from aiohttp.web import FileResponse

import logging
from datetime import timedelta
 
# 此处引入了几个异步处理的库
import asyncio
import async_timeout
import aiohttp
from homeassistant.components.http import HomeAssistantView
 
import voluptuous as vol
 
# aiohttp_client将aiohttp的session与hass关联起来
# track_time_interval需要使用对应的异步的版本
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
 
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (CONF_NAME,ATTR_ATTRIBUTION, ATTR_FRIENDLY_NAME, TEMP_CELSIUS)
from homeassistant.helpers.entity import Entity
import homeassistant.helpers.config_validation as cv
import homeassistant.util.dt as dt_util
 
_LOGGER = logging.getLogger(__name__)
 
TIME_BETWEEN_UPDATES = timedelta(seconds=600)

DOMAIN = 'shbus'
VERSION = '1.0'

CONF_DIRECTION = "direction"
CONF_STOP_ID = "stop_id"

 
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_NAME): cv.string,
    vol.Optional(CONF_DIRECTION, default="1"): cv.string,
    vol.Optional(CONF_STOP_ID, default=''): cv.string,
})

SH_BUS = None

@asyncio.coroutine
def async_setup_platform(hass, config, async_add_devices, discovery_info=None):
    
 
    name = config.get(CONF_NAME)
    direction = config.get(CONF_DIRECTION)
    stop_id = config.get(CONF_STOP_ID)
        
    _install_tips = "安装成功"    
    bus = Bus()
    # 获取站点名称
    stop_name = ''
    try:        
        stops = bus.query_router(name, direction)
        if stop_id != "":
            _list = list(filter(lambda x: x['stop_id'] == stop_id + '.',stops['stops']))        
            if len(_list) > 0:
                stop_name = _list[0]['stop_name']
    except Exception as e:
        _install_tips = "安装失败（没有找到公交线路）"
    
    # 提示
    _LOGGER.info('''
-------------------------------------------------------------------

    上海公交传感器【作者QQ：635147515】

    版本：''' + VERSION + '''    

    介绍：这是一个上海公交的实时到站插件

    项目地址：https://github.com/shaonianzhentan/ha_cloud_music

    安装信息：

        安装提示：''' + _install_tips + '''
        
        公交名称：''' + name + '''
        
        站点名称：''' + stop_name + '''
        
        公交方向：''' + direction + '''【''' + stops['from'] + '''】到【''' + stops['to'] + '''】
    
-------------------------------------------------------------------''')
    global SH_BUS
    SH_BUS = bus    
    hass.http.register_view(HassGateView)
    # 注册shbus状态卡片
    hass.components.frontend.add_extra_js_url(hass, '/' + DOMAIN + '-api?v=' + VERSION)
    async_add_devices([ShBus(name, hass, bus, stops, stop_id, stop_name)], True)
 
##### 网关控制
class HassGateView(HomeAssistantView):
    """View to handle Configuration requests."""

    url = '/' + DOMAIN + '-api'
    name = DOMAIN
    requires_auth = False

    async def get(self, request):    
        _raw_path = request.rel_url.raw_path
        _path = os.path.dirname(__file__) + '/more-info-shbus.js'
        return FileResponse(_path)

    async def post(self, request):
        """Update state of entity."""
        response = await request.json()
        if 'name' in response and 'direction' in response and 'stop_id' in response:
            response = SH_BUS.query_stop(response['name'], response['direction'], response['stop_id'])

        return self.json(response)
    
 
##### 上海公交
class ShBus(Entity):
 
    def __init__(self, name, hass, bus, stops, stop_id, stop_name):
        """初始化."""
        self._object_id = name
        self._friendly_name = name
        self._icon = "mdi:bus"
        self._unit_of_measurement = "分钟" 
        self._state = None
        self._hass = hass
        self._bus = bus
        # 要监听的站点
        self._stop_id = stop_id
        self._direction = stops['direction']
                
        self._attr = {
            "from": stops['from'],
            "to": stops['to'], 
            "stop_name": stop_name,
            "start_at": stops['start_at'], 
            "end_at": stops['end_at'], 
            "bus_status": None,
            "direction": self._direction,            
            "stop_interval": None,
            "time": None,
            "distance": None,
            "plate_number": None,
            "update_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            "stops":  json.dumps(stops['stops'],ensure_ascii=False),            
        }
 
    @property
    def name(self):
        """返回实体的名字."""
        return self._object_id
 
    @property
    def registry_name(self):
        """返回实体的friendly_name属性."""
        return self._friendly_name
 
    @property
    def state(self):
        """返回当前的状态."""
        return self._state
 
    @property
    def icon(self):
        """返回icon属性."""
        return self._icon
 
    @property
    def unit_of_measurement(self):
        """返回unit_of_measuremeng属性."""
        return self._unit_of_measurement
 
    @property
    def device_state_attributes(self):
        """设置其它一些属性值."""
        if self._state is not None:
            attr = self._attr
            return {
                "name": self.name,
                "from": attr['from'],
                "to": attr['to'],              
                "stop_name": attr['stop_name'],
                "stop_interval": attr['stop_interval'],
                "time": attr['time'],
                "distance": attr['distance'],
                "start_at": attr['start_at'], 
                "end_at": attr['end_at'], 
                "direction": self._direction,
                "plate_number": attr['plate_number'],
                "bus_status": attr['bus_status'],
                "update_at": attr['update_at'],
                "stops": attr['stops'],
                "custom_ui_more_info": "more-info-shbus",
            }
 
    @asyncio.coroutine
    def async_update(self):
        """update函数变成了async_update.""" 
        _state = -1
        
        if self._stop_id != '':
            r = self._bus.query_stop(self._friendly_name, self._direction, self._stop_id)
            self._attr['plate_number'] = r['plate_number']
            self._attr['stop_interval'] = r['stop_interval']
            _time = ''
            # 如果当前有车运行
            if r['status'] == 'running':
                _time = int(r['time'])                
                _state = math.floor(_time / 60)
            
            self._attr['time'] = _time
            self._attr['distance'] = r['distance']            
            self._attr['bus_status'] = r['status']
            self._attr['update_at'] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            self._state = _state
        else:
            self._state = _state

            


#######################################支持的公交路线#######################################
Routers = ['青纪线', '青浦1路', '1001路', '1002路', '1003路', '1004路', '1005路', '1006路', '1007路', '1008路', '1009路', '1010路', '1011路', '1012路', '1013路', '1015路', '1016路', '1017路', '1018路', '1019路', '1020路', '1021路', '1022路', '1023路', '1024路', '1025路', '1026路', '1027路', '1028路', '1029路', '1030路', '1031路', '1032路', '1033路', '1034路', '1035路', '1036路', '1037路', '1038路', '1039路', '1040路', '1041路', '1042路', '1043路', '1045路', '1046路', '1047路', '1048路', '1049路', '1050路', '1051路', '1052路', '1053路', '1054路', '1055路', '1056路', '1057路', '1058路', '1059路', '1060路', '1061路', '1062路', '1063路', '1064路', '1065路', '1066路', '1067路', '1068路', '1069路', '1070路', '1071路', '1072路', '1073路', '1074路', '1075路', '1077路', '1078路', '1079路', '1080路', '1081路', '1082路', '1083路', '1085路', '1086路', '1087路', '1088路', '1089路', '1090路', '1091路', '1092路', '1093路', '1094路', '1095路', '1096路', '1097路', '1098路', '1099路', '1100路', '1101路', '1102路', '1103路', '1104路', '1105路', '1106路', '1107路', '1108路', '1109路', '1110路', '1111路', '1112路', '1113路', '1115路', '1116路', '1117路', '1118路', '1120路', '1121路', '1122路', '119路', '130路', '161路', '163路', '167路', '169路', '174路', '175路', '177路', '181路', '182路', '183路', '188南汇', '219路', '313路', '314路', '338路', '339路', '451路', '453路', '454路', '455路', '572路', '572路区间1(三林)路', '573路', '576路', '581路', '583路', '604路', '610路', '611路', '614路', '636路', '638路', '639路', '640路', '772路', '774路', '775路', '777路', '778路', '779路', '780路', '781路', '782路', '783路', '784路', '785路', '786路', '787路', '789路', '790路', '791路', '792路', '793路', '794路', '795路', '796路', '798路', '799路', '815路', '81路', '82路', '83路', '843路', '84路', '85路', '863路', '871路', '915路', '955路', '961路', '969路', '970路', '971路', '976路', '977路', '978路', '980路', '981路', '983路', '984路', '985路', '986路', '986路区间', '987路', '988路', '989路', '990路', '991路', '991路区间', '992路', '993路', '995路', '北蔡1路', '北蔡2路', '蔡陆专线', '曹路1路', '曹路2路', '曹路3路', '曹路4路', '川奉专线', '川芦专线', '川沙2路', '川沙3路', '川沙4路', '川沙5路', '大泥专线', '大桥六线', '大桥四线', '大桥五线', '大团2路', '国际旅游度假区2路', '国际旅游度假区3路', '航大专线', '航头3路', '合庆1路', '鹤莘线', '沪川线', '沪南线', '花木1路', '花木2路', '惠南10路', '惠南11路', '惠南1路', '惠南2路', '惠南3路', '惠南4路', '惠南5路', '惠南6路', '惠南8路', '机场八线', '机场七线', '金桥1路', '老港1路', '两滨专线', '六灶2路', '龙大专线', '龙东专线', '龙港快线', '龙惠专线', '龙临专线', '龙芦专线', '龙新芦专线', '芦潮港1路', '芦杜专线', '陆家嘴金融城1路', '陆家嘴金融城2路', '陆家嘴金融城3路', '陆家嘴金融城4路', '陆家嘴金融城环线', '闵行20路', '南川线', '南闵专线', '南南线', '南新专线', '南园1路', '泥城1路', '泥城2路', '泥城4路', '泥城5路', '浦东10路', '浦东12路', '浦东18路', '浦东19路', '浦东1路', '浦东20路', '浦东22路', '浦东23路', '浦东24路', '浦东25路', '浦东27路', '浦东28路', '浦东29路', '浦东2路', '浦东30路', '浦东31路', '浦东32路', '浦东33路', '浦东35路', '浦东36路', '浦东37路', '浦东38路', '浦东39路', '浦东3路', '浦东41路', '浦东42路', '浦东4路', '浦东50路', '浦东50路区间', '浦东51路', '浦东52路', '浦东6路', '浦东7路', '浦东8路', '浦东9路', '浦江11路', '浦江1路', '浦江2路', '浦江3路', '浦江4路', '浦江5路', '浦江6路', '浦江7路', '三林1路', '申崇二线', '申崇六线', '申崇六线B', '申崇四线', '申崇四线区间', '申港1路', '申港3路', '申港4路', '施崂专线', '书院2路', '书院3路', '隧道九线', '隧道六线', '隧道三线', '隧道一线', '外高桥1路', '外高桥3路', '外高桥4路', '万祥2路', '新场1路', '新场2路', '新场3路', '新场5路', '新川专线', '新芦专线', '宣桥1路', '洋山专线', '洋山专线区间', '张江1路', '张江环线', '张南专线', '周康10路', '周康1路', '周康2路', '周康3路', '周康4路', '周康5路', '周康6路', '周康9路', '周南线', '祝桥1路', '祝桥2路', '祝桥3路', '11路', '1212路', '1222路', '1226路', '1231路', '1238路', '138路', '146路', '17路', '18路', '26路', '42路', '64路', '715路', '736路', '805路', '821路', '874路', '875路', '876路', '911路', '920路', '926路', '927路', '929路', '930路', '931路', '932路', '96路', '974路', '975路', '万周专线', '隧道八线', '上佘定班线', '109路', '111路', '1202路', '1203路', '1204路', '1204B', '1210路', '122路', '131路', '144路', '150路', '152路', '157路', '162路', '166路', '171路', '176路', '178路', '180路', '189路', '189区间', '198路', '205路', '218路', '257路', '43路', '49路', '50路', '56路', '56区间', '700路', '703路', '703B路', '704路', '704B路', '707路', '708路', '712路', '714路', '718路', '720路', '729路', '731路', '732路', '735路', '747路', '755路', '759路', '761路', '763路', '764路', '770路', '820路', '89路', '92路', '92B路', '958路', '闵行33路', '古美环线', '徐闵夜宵专线', '徐闵线', '松闵线', '810路', '江川3路', '莘庄1路', '莘庄2路', '莘庄3路', '莘车线', '虹桥枢纽4路', '闵东线', '闵吴线', '闵行29路', '143区间', '闵行16路', '闵行1路', '闵行22路', '闵马线', '闵行30路', '100路', '102路', '103路', '115路', '1201路', '1218路', '123路', '123区间', '124路', '140路', '142路', '147路', '168路', '179路', '220路', '222路', '405路', '406路', '47路', '522路', '55路', '559路', '577路', '59路', '597路', '60路', '61路', '66路', '66区间', '70路', '716路', '723路', '749路', '758路', '79路', '80路', '819路', '842路', '870路', '90路', '942路', '960路', '966路', '97路', '99路', '大桥三线', '1219路', '13路', '134路', '135路', '137路', '139路', '14路', '145路', '15路', '155路', '19路', '20路', '21路', '22路', '23路', '24路', '25路', '28路', '33路', '36路', '37路', '538路', '6路', '746路', '751路', '8路', '866路', '868路', '921路', '934路', '939路', '67路', '836路', '65路', '118路', '730路', '510路', '951路', '937路', '962路', '912路', '831路', '城桥2路', '1711路', '1721路', '1731路', '崇明东滩1路', '南东专线', '南同专线', '南堡专线', '南建专线', '南江专线', '南海二线', '南海线', '南牛线', '南红专线', '南裕专线', '南跃线', '南隆专线', '南风线', '城桥1路', '堡七线', '堡四线', '堡红线', '堡胜专线', '堡进线', '堡陈专线', '堡陈中线', '堡陈北线', '崇明乡村10路', '崇明乡村11路', '崇明乡村1路', '崇明乡村3路', '崇明乡村4路', '崇明乡村5路', '崇明乡村6路', '崇明乡村7路', '崇明乡村8路', '崇明乡村9路', '横沙2路', '横沙3路', '申崇一线', '申崇三线', '申崇三线区间', '申崇四线区间', '申崇二线', '申崇六线', '申崇六线B(崇明巴士)', '申崇四线', '长兴1路', '长兴2路', '长兴3路', '长兴4路', '长南线', '陈凤线', '陈前线', '04路', '107路', '108区间', '110路', '1208路', '1209路', '151路', '165路', '185路', '187路', '206路', '210路', '253路', '40路', '46路', '46路区间', '108路', '528路', '547路', '551路', '58路', '68路', '702路', '705路', '722路', '727路', '741路', '745路', '762路', '767路', '78路', '845路', '849路', '850路', '853路', '854路', '862路', '95路', '959路', '98路', '宝山19路', '宝山20路', '宝山22路', '申方专线', '104路', '1220路', '184路', '41路', '607路', '609路', '615路', '624路', '627路', '628路', '629路', '630路', '632路', '1084路', '733路', '734路', '818路', '824路', '869路', '933路', '973路', '上川专线', '合庆2路', '塘南专线', '外高桥2路', '大桥一线', '孙桥1路', '徐川专线', '浦东11路', '浦东13路', '浦东17路', '申川专线', '浦东15路', '隧道二线', '高川专线', '178路大站车', '864路', '南堡支线', '南新专线（崇明）', '01路', '113路', '120路', '1207路', '121路', '1216路', '1217路', '1221路', '1250路', '1251路', '141路', '149路', '158路', '173路', '190路', '192路', '193路', '195路', '197路', '44路', '48路', '519路', '54路', '548路', '57路', '709路', '71路', '71路区间', '72路', '721路', '725路', '739路', '74路', '748路', '752路', '753路', '754路', '757路', '76路', '765路', '776路', '803路', '804路', '807路', '808路', '809路', '825路', '830路', '834路', '855路', '867路', '87路', '88路', '91路', '93路', '941路', '941路跨线定班', '944路', '946路', '新泾1路', '松亭石专线', '松江12路', '沪松专线', '虹桥枢纽1路', '上石线', '松卫专线', '松卫线', '石梅线', '石青专线', '虹桥枢纽7路', '南金线', '朱松线', '朱泾五路', '1650路', '松新枫线', '枫梅线', '枫泾七路', '莘金专线', '金张卫支线', '金枫线', '金漕线', '金石线', '青枫专线', '南卫线', '塘卫线', '奉卫线', '朱卫专线', '朱卫线', '朱钱卫线', '枫戚快线', '浦卫专线', '浦卫线', '石南专线', '石漕线', '石胡专线', '亭林三路', '山阳一路', '山阳一路区间', '山阳二路', '山阳二路工业区', '张堰一路', '张堰二路', '漕泾一路', '1651路', '石化一线', '石化三线', '金山1路', '金山2路', '金山3路', '金山4路', '金山5路', '金山6路', '金山7路', '金山8路', '金山9路', '金山9路区间', '金山卫一路', '金山卫二路', '金山工业区一路', '金山工业区二路', '116B', '52路', '552路', '554路', '823路', '申崇五线', '申崇五线班车', '1602路', '宝山12路', '宝山13路', '宝山14路', '宝山15路', '宝山16路', '宝山1路', '宝山2路', '宝山3路', '宝山4路', '宝山6路', '宝山81路', '宝山83路', '宝山84路', '宝山85路', '160路', '51路', '537路', '726路', '817路', '宝山11路', '159路', '172路', '527路', '701路', '728路', '813路', '508路', '719路', '952路', '952B', '宝山10路', '宝山18路', '宝山5路', '宝山7路', '宝山29路', '宝山30路', '宝山31路', '宝山36路', '宝山93路', '811路', '711路', '841路', '963路', '宝山21路', '宝山23路', '宝山8路', '132路', '133路', '502路', '713路', '760路', '812路', '1205路', '1206路', '327路', '45路', '858路', '94路', '947路', '828路', '909路', '950路', '长征1路', '826路', '北安线', '北安跨线', '224路', '252路', '309路', '340路', '561路', '69路', '740路', '上嘉线', '105路', '136路', '319路', '63路', '717路', '768路', '948路', '106路', '112路', '112区间', '129路', '216路', '724路', '743路', '766路', '837路', '838路', '832路', '833路', '856路', '沪唐专线', '737路', '738路', '827路', '829路', '846路', '923路', '101路', '117路', '1223路', '323路', '62路', '742路', '744路', '750路', '859路', '1228路', '50路区间', '1600路', '1603路', '1604路', '1605路', '1606路', '1607路', '1609路', '宝山82路', '宝山86路', '宝山9路', '宝山17路', '宝山25路', '宝山89路', '宝山90路', '宝山91路', '宝山92路', '宝山95路', '839路', '宝山88路', '宝山87路', '1611路', '1601路', '崇明东滩2路', '1606路', '罗泾班线', '南堡二线', '横长线', '302路', '322路', '1608路', '1712路', '307路', '325路', '306路', '310路', '308路', '329路', '303路', '305路', '312路', '321路', '332路', '318路', '324路', '301路', '隧道夜宵一线', '311路', '316路', '320路', '328路', '341路', '315路', '330路', '304路', '317路', '326路', '342路', '申崇二线区间', '1014路', '1227路', '闵行28路', '闵行36路', '浦东14路', '1229路', '143路', '1610路', '1612路', '宝山27路', '宝山28路', '宝山35路', '陆安高速', '陆安高速B', '上奉专线', '南团线', '奉贤10路', '奉贤11路', '奉贤12路', '奉贤13路', '奉贤15路', '奉贤16路', '奉贤18路', '奉贤1路', '奉贤21路', '奉贤22路', '奉贤23路', '奉贤26路', '奉贤27路', '奉贤3路', '奉贤8路', '奉贤9路', '庄莘线', '庄莘线区间', '庄行1线', '庄行2线', '柘林1线', '柘林2线', '海湾1线', '西莲线', '南华专线', '南叶线', '南松专线', '南梅线', '南江线', '南燎专线', '南航线', '南金线', '南青专线', '奉贤24路', '奉贤25路', '莘南专线', '莘南高速线', '虹桥枢纽5路', '南五线', '奉南线', '南头专线', '南邵线', '四团1线', '四团2线', '四团3线', '奉卫线', '奉城1线', '奉城2线', '奉城3线', '奉燎线', '江五线', '沪塘专线', '海湾3线', '莘团线', '邵鹤线', '金汇1线', '青村1线', '青村2线', '嘉定12路', '嘉定13路', '嘉定52路', '嘉定65路', '嘉松线', '菊园1路', '虹桥枢纽9路', '上嘉线', '沪嘉专线', '嘉定127路', '安亭8路', '嘉定16路', '嘉定17路', '江桥4路', '外罗线', '嘉定3路', '嘉定4路', '嘉定63路', '嘉定62路', '嘉定57路', '嘉唐华线', '嘉定67路', '嘉定58路', '嘉定56路', '嘉定5路', '马陆1路', '江桥1路', '安亭2路', '嘉定7路', '安亭4路', '嘉定11路', '真新1路', '安亭6路', '嘉定53路', '安亭7路', '南翔4路', '南翔5路', '嘉定15路', '闵行11路', '闵行26路', '虹桥枢纽10路', '松江13路', '松江16路', '松江1路', '松江20路', '松江21路', '松江22路', '松江23路', '松江24路', '松江25路', '松江27路', '松江28路', '松江31路', '松江33路', '松江36路', '松江3路', '松江4路', '松江64路', '松江66路', '松江7路', '松江99路', '松江9路', '松江11路', '松江17路']

#######################################异常类#######################################
           
class InvalidParameterException(Exception):
    def __init__(self, error, error_msg, status_code=None, payload=None):
        Exception.__init__(self)
        self.error = error
        self.error_msg = error_msg

        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or ())
        rv['error'] = self.error
        rv['error_msg'] = self.error_msg

        return rv
           
#######################################公交查询类#######################################
class Bus:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 10_3_2 like Mac OS X) AppleWebKit/603.2.4 '
                          '(KHTML, like Gecko) Mobile/14F89 MicroMessenger/6.5.10 NetType/WIFI Language/zh_CN'
        }
        self.session_file = os.path.dirname(__file__) + '/session.log'
        self.homepage_url = 'https://shanghaicity.openservice.kankanews.com/'
        self.query_router_url = 'https://shanghaicity.openservice.kankanews.com/public/bus'
        self.query_sid_url = 'https://shanghaicity.openservice.kankanews.com/public/bus/get'
        self.query_router_details_url = 'https://shanghaicity.openservice.kankanews.com/public/bus/mes/sid/'
        self.query_stop_url = 'https://shanghaicity.openservice.kankanews.com/public/bus/Getstop'

    def _homepage(self):
        r = self.s.get(self.homepage_url, headers=self.headers)

        return r

    def _query_router_page(self):
        self.headers['Referer'] = self.homepage_url
        r = self.s.get(self.query_router_url, headers=self.headers)

        return r

    def _query_sid(self, router_name):
        data = {'idnum': router_name}
        r = self.s.post(self.query_sid_url, data=data, headers=self.headers)
        sid = r.json()['sid']

        return sid

    def _query_router_details_page(self, sid, direction='0'):
        self.headers['Referer'] = self.query_router_url
        url = self.query_router_details_url + sid + '?stoptype=' + direction
        r = self.s.get(url, headers=self.headers)

        return r

    def _query_stop(self, sid, direction, stop_id):
        data = {'stoptype': direction, 'stopid': stop_id, 'sid': sid}
        self.headers['Content-Type'] = 'application/x-www-form-urlencoded'
        self.headers['Referer'] = self.query_router_details_url

        r = self.s.post(self.query_stop_url, data=data, headers=self.headers)

        return r

    def _init_request(self, router_name):
        self._check_routers(router_name)

        if os.path.exists(self.session_file):
            with open(self.session_file, 'rb') as f:
                session = pickle.load(f)

                if session['expired_at']+1800 < time.time():
                    # session expired
                    self._make_session()
                else:
                    # read session from cache
                    self.s = session['session']

        else:
            # session not exists
            self._make_session()

        # 第三步：查询公交路线对应的sid
        sid = self._query_sid(router_name)

        return sid

    def _make_session(self):
        self.s = requests.Session()

        # 第一步：加载首页
        self._homepage()

        # 第二部：加载查询页面
        self._query_router_page()

        with open(self.session_file, 'wb') as f:
            session = {
                'session': self.s,
                'expired_at':  time.time()
            }
            pickle.dump(session, f)

    def _check_routers(self, router_name):
        if router_name not in Routers:
            raise InvalidParameterException('router_not_exists', '不存在该公交线路', 400)

    def query_stop(self, router_name, direction, stop_id):
        sid = self._init_request(router_name)

        # 查询公交到站信息
        r = self._query_stop(sid, direction, stop_id)

        res = r.json()
        if type(res) is list:
            res = res[0]
            return {
                'router_name': res['@attributes']['cod'],
                'direction': direction,
                'plate_number': res['terminal'],
                'stop_interval': res['stopdis'],
                'distance': res['distance'],
                'time': res['time'],
                'status': 'running'
            }
        else:
            return {
                'router_name': router_name,
                'direction': direction,
                'plate_number': '',
                'stop_interval': '',
                'distance': '',
                'time': '',
                'status': 'waiting'
            }

    def query_router(self, router_name, direction='0'):
        self.sid = self._init_request(router_name)

        # 进入公交线路明细页面
        r = self._query_router_details_page(self.sid, direction)

        soup = BeautifulSoup(r.text.encode(r.encoding), 'lxml')

        stations = soup.select('div.upgoing.cur span')
        from_station = stations[0].string
        to_station = stations[1].string

        strat_at = soup.select('div.upgoing.cur em.s')[0].string
        end_at = soup.select('div.upgoing.cur em.m')[0].string

        stations = soup.select('div.station')
        stops = []
        for station in stations:
            router = {}
            for c in station.children:
                if c.name == 'span':
                    if c.attrs['class'][0] == 'num':
                        router['stop_id'] = c.string
                    elif c.attrs['class'][0] == 'name':
                        router['stop_name'] = c.string
            stops.append(router)

        return {
            'from': from_station,
            'to': to_station,
            'start_at': strat_at,
            'end_at': end_at,
            'direction': direction,
            'stops': stops
        }

    def query_router_details(self, router_name, direction='0'):
        router = self.query_router(router_name, direction)

        stops = router['stops']

        for stop in stops:
            # 查询公交到站信息
            r = self._query_stop(self.sid, direction, stop['stop_id'])

            res = r.json()
            if type(res) is list:
                res = res[0]
                stop['plate_number'] = res['terminal']
                stop['stop_interval'] = res['stopdis']
                stop['distance'] = res['distance']
                stop['time'] = res['time']
                stop['status'] = 'running'
            else:
                stop['plate_number'] = ''
                stop['stop_interval'] = ''
                stop['distance'] = ''
                stop['time'] = ''
                stop['status'] = 'waiting'

        return router    
 