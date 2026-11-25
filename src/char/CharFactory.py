from src.Labels import Labels
from src.char.Aemeath import Aemeath
from src.char.Aalto import Aalto
from src.char.Augusta import Augusta
from src.char.Baizhi import Baizhi
from src.char.BaseChar import BaseChar, CharType, Elements, get_default_buff_time
from src.char.Brant import Brant
from src.char.Calcharo import Calcharo
from src.char.Camellya import Camellya
from src.char.Cantarella import Cantarella
from src.char.Carlotta import Carlotta
from src.char.Cartethyia import Cartethyia
from src.char.Changli import Changli
from src.char.Chisa import Chisa
from src.char.Chixia import Chixia
from src.char.Ciaccona import Ciaccona
from src.char.Danjin import Danjin
from src.char.Denia import Denia
from src.char.Douling import Douling
from src.char.Encore import Encore
from src.char.Galbrena import Galbrena
from src.char.Rover import Rover
from src.char.Hiyuki import Hiyuki
from src.char.Hsin import Hsin
from src.char.Iuno import Iuno
from src.char.Jianxin import Jianxin
from src.char.Jinhsi import Jinhsi
from src.char.JingRan import JingRan
from src.char.Jiyan import Jiyan
from src.char.Lily import Lily
from src.char.Lingyang import Lingyang
from src.char.Linnai import Linnai
from src.char.Lucilla import Lucilla
from src.char.Lucy import Lucy
from src.char.Lumi import Lumi
from src.char.Luhesi import Luhesi
from src.char.Lupa import Lupa
from src.char.Mortefi import Mortefi
from src.char.Mornye import Mornye
from src.char.Phoebe import Phoebe
from src.char.Phrolova import Phrolova
from src.char.Qingxiao import Qingxiao
from src.char.Qiuyuan import Qiuyuan
from src.char.Rebecca import Rebecca
from src.char.Roccia import Roccia
from src.char.Sanhua import Sanhua
from src.char.ShoreKeeper import ShoreKeeper
from src.char.Suisui import Suisui
from src.char.Suoming import Suoming
from src.char.Taoqi import Taoqi
from src.char.Verina import Verina
from src.char.Xiangliyao import Xiangliyao
from src.char.Xigelika import Xigelika
from src.char.Yinlin import Yinlin
from src.char.Yangyang import Yangyang
from src.char.YangYangSp import YangYangSp
from src.char.Youhu import Youhu
from src.char.Yuanwu import Yuanwu
from src.char.Zani import Zani
from src.char.Zhezhi import Zhezhi
from src.char.CustomCharLoader import load_team_char_class, normalize_team

_char_dict_raw = {
    Labels.char_aalto: {'cls': Aalto, 'char_type': CharType.SUB_DPS,
                             'ring_index': Elements.WIND},
    Labels.char_yangyang: {'cls': Yangyang, 'char_type': CharType.SUB_DPS, 'ring_index': Elements.WIND},
    Labels.yangyang_sp: {'cls': YangYangSp, 'char_type': CharType.MAIN_DPS,
                         'ring_index': Elements.HAVOC},
    Labels.char_yinlin: {'cls': Yinlin, 'char_type': CharType.SUB_DPS,
                         'ring_index': Elements.ELECTRIC},
    Labels.char_verina: {'cls': Verina, 'char_type': CharType.HEALER,
                         'ring_index': Elements.SPECTRO},
    Labels.char_shorekeeper: {'cls': ShoreKeeper, 'char_type': CharType.HEALER,
                              'ring_index': Elements.SPECTRO},
    Labels.char_suisui: {'cls': Suisui, 'char_type': CharType.HEALER},
    Labels.char_taoqi: {'cls': Taoqi, 'char_type': CharType.HEALER,
                        'ring_index': Elements.HAVOC},
    (Labels.char_rover, Labels.char_rover_male): {'cls': Rover, 'char_type': CharType.MAIN_DPS},
    Labels.char_encore: {'cls': Encore, 'char_type': CharType.MAIN_DPS,
                         'ring_index': Elements.FIRE},
    Labels.char_jianxin: {'cls': Jianxin, 'char_type': CharType.HEALER,
                          'ring_index': Elements.WIND},
    (Labels.char_sanhua, Labels.char_sanhua2): {'cls': Sanhua, 'char_type': CharType.SUB_DPS,
                                                'ring_index': Elements.ICE},
    (Labels.char_jinhsi, Labels.char_jinhsi2): {'cls': Jinhsi, 'char_type': CharType.MAIN_DPS,
                                                'ring_index': Elements.SPECTRO},
    Labels.char_yuanwu: {'cls': Yuanwu, 'char_type': CharType.SUB_DPS,
                         'ring_index': Elements.ELECTRIC},
    (Labels.chang_changli, Labels.char_changli2): {'cls': Changli, 'char_type': CharType.MAIN_DPS,
                                                   'ring_index': Elements.FIRE},
    Labels.char_chixia: {'cls': Chixia, 'char_type': CharType.MAIN_DPS,
                         'ring_index': Elements.FIRE},
    Labels.char_danjin: {'cls': Danjin, 'char_type': CharType.SUB_DPS,
                         'ring_index': Elements.HAVOC},
    Labels.char_baizhi: {'cls': Baizhi, 'char_type': CharType.HEALER,
                         'ring_index': Elements.ICE},
    Labels.char_calcharo: {'cls': Calcharo, 'char_type': CharType.MAIN_DPS,
                           'ring_index': Elements.ELECTRIC},
    Labels.char_jiyan: {'cls': Jiyan, 'char_type': CharType.MAIN_DPS,
                        'ring_index': Elements.WIND},
    Labels.char_lingyang: {'cls': Lingyang, 'char_type': CharType.MAIN_DPS,
                                'ring_index': Elements.ICE},
    Labels.char_mortefi: {'cls': Mortefi, 'char_type': CharType.SUB_DPS,
                          'ring_index': Elements.FIRE},
    Labels.char_zhezhi: {'cls': Zhezhi, 'char_type': CharType.SUB_DPS,
                         'ring_index': Elements.ICE},
    Labels.char_xiangliyao: {'cls': Xiangliyao, 'char_type': CharType.MAIN_DPS,
                             'ring_index': Elements.ELECTRIC},
    Labels.char_camellya: {'cls': Camellya, 'char_type': CharType.MAIN_DPS,
                           'ring_index': Elements.HAVOC},
    Labels.char_youhu: {'cls': Youhu, 'char_type': CharType.HEALER,
                        'ring_index': Elements.ICE},
    (Labels.char_carlotta, Labels.char_carlotta2): {'cls': Carlotta, 'char_type': CharType.MAIN_DPS,
                                                    'ring_index': Elements.ICE},
    Labels.char_roccia: {'cls': Roccia, 'char_type': CharType.SUB_DPS, 'ring_index': Elements.HAVOC},
    Labels.char_phoebe: {'cls': Phoebe, 'char_type': CharType.SUB_DPS, 'ring_index': Elements.SPECTRO},
    Labels.char_brant: {'cls': Brant, 'char_type': CharType.HEALER, 'ring_index': Elements.FIRE},
    Labels.char_cantarella: {'cls': Cantarella, 'char_type': CharType.HEALER, 'ring_index': Elements.HAVOC},
    (Labels.char_zani, Labels.char_zani2): {'cls': Zani, 'char_type': CharType.MAIN_DPS,
                                            'ring_index': Elements.SPECTRO},
    Labels.char_ciaccona: {'cls': Ciaccona, 'char_type': CharType.SUB_DPS, 'ring_index': Elements.WIND},
    Labels.char_cartethyia: {'cls': Cartethyia, 'char_type': CharType.MAIN_DPS, 'ring_index': Elements.WIND},
    Labels.char_lupa: {'cls': Lupa, 'char_type': CharType.SUB_DPS, 'ring_index': Elements.FIRE},
    Labels.char_phrolova: {'cls': Phrolova, 'char_type': CharType.MAIN_DPS, 'ring_index': Elements.HAVOC},
    Labels.Augusta: {'cls': Augusta, 'char_type': CharType.MAIN_DPS, 'ring_index': Elements.ELECTRIC},
    Labels.char_iuno: {'cls': Iuno, 'char_type': CharType.SUB_DPS,
                       'ring_index': Elements.WIND},
    Labels.char_galbrena: {'cls': Galbrena, 'char_type': CharType.MAIN_DPS, 'ring_index': Elements.FIRE},
    Labels.char_chouyuan: {'cls': Qiuyuan, 'char_type': CharType.SUB_DPS, 'ring_index': Elements.WIND},
    (Labels.char_chisa, Labels.char_chisa2): {'cls': Chisa, 'char_type': CharType.HEALER, 'buff_time': 20,
                                              'ring_index': Elements.HAVOC},
    Labels.char_denia: {'cls': Denia, 'char_type': CharType.SUB_DPS, 'buff_time': 14, 'ring_index': Elements.FIRE},
    Labels.char_douling: {'cls': Douling, 'char_type': CharType.HEALER, 'ring_index': Elements.ELECTRIC},
    (Labels.char_linnai, Labels.char_linnai2): {'cls': Linnai, 'char_type': CharType.SUB_DPS,
                                                'ring_index': Elements.SPECTRO},
    (Labels.char_moning, Labels.char_moning_new): {'cls': Mornye, 'char_type': CharType.HEALER,
                                                   'ring_index': Elements.FIRE},
    Labels.char_aemeath: {'cls': Aemeath, 'char_type': CharType.MAIN_DPS, 'ring_index': Elements.FIRE},
    Labels.char_xigelika: {'cls': Xigelika, 'char_type': CharType.MAIN_DPS, 'ring_index': Elements.WIND},
    Labels.char_luhesi: {'cls': Luhesi, 'char_type': CharType.MAIN_DPS, 'ring_index': Elements.SPECTRO},
    (Labels.char_hiyuki, Labels.char_hiyuki2): {'cls': Hiyuki, 'char_type': CharType.MAIN_DPS,
                                             'ring_index': Elements.ICE},
    Labels.char_lucilla: {'cls': Lucilla, 'char_type': CharType.SUB_DPS, 'ring_index': Elements.ICE,
                          'target_box_short_combat_check': True},
    Labels.char_lucy: {'cls': Lucy, 'char_type': CharType.MAIN_DPS, 'ring_index': Elements.SPECTRO},
    Labels.char_lumi: {'cls': Lumi, 'char_type': CharType.SUB_DPS, 'ring_index': Elements.ELECTRIC},
    Labels.char_rebecca: {'cls': Rebecca, 'char_type': CharType.SUB_DPS, 'ring_index': Elements.ELECTRIC},
    Labels.char_qingxiao: {'cls': Qingxiao, 'char_type': CharType.MAIN_DPS, 'ring_index': Elements.WIND},
    Labels.char_jingran: {'cls': JingRan, 'char_type': CharType.MAIN_DPS, 'ring_index': Elements.FIRE},
    Labels.char_hsin: {'cls': Hsin, 'char_type': CharType.MAIN_DPS, 'ring_index': Elements.ELECTRIC},
    Labels.char_suoming: {'cls': Suoming, 'char_type': CharType.SUB_DPS, 'buff_time': 8,
                         'ring_index': Elements.ELECTRIC},
    Labels.char_lily: {'cls': Lily, 'char_type': CharType.HEALER, 'buff_time': 30,
                      'ring_index': Elements.SPECTRO},
}

char_dict = {}
for keys, value in _char_dict_raw.items():
    value = dict(value)
    value.setdefault('buff_time', get_default_buff_time(value.get('char_type', CharType.MAIN_DPS)))
    template_names = keys if isinstance(keys, tuple) else (keys,)
    value['canonical_name'] = template_names[0]
    value['template_names'] = template_names
    for key in template_names:
        char_dict[key] = value

char_names = char_dict.keys()


def _get_char_type(task, info):
    return info.get('char_type', CharType.MAIN_DPS)


def _get_buff_time(task, info):
    char_type = _get_char_type(task, info)
    return info.get('buff_time', get_default_buff_time(char_type))


def _apply_char_config(task, char, info):
    if char and info:
        char.char_name = info['canonical_name']
        char.set_char_type(_get_char_type(task, info))
        char.set_buff_time(_get_buff_time(task, info))
        char.target_box_short_combat_check = info.get('target_box_short_combat_check', False)
    return char


def _find_registered_char(task, box, info):
    template_names = info['template_names']
    if len(template_names) == 1:
        return task.find_one(template_names[0], box=box, threshold=0.6)
    return task.find_best_match_in_box(box, template_names, threshold=0.6)


def get_char_by_pos(task, box, index, old_char):
    highest_confidence = 0
    info = None
    name = "unknown"
    char = None
    if old_char and old_char.confidence > 0.92 and old_char.char_name in char_names:
        info = char_dict.get(old_char.char_name)
        char = _find_registered_char(task, box, info)
        if char:
            cls = info.get('cls')
            # 工坊自定义角色类是内置类的"兄弟"类(同名、都直接继承 BaseChar), 不是内置类的子类。
            # isinstance(old_char, cls) 对自定义实例恒为 False, 会把工坊代码误判成"角色变了",
            # 每轮用内置类重建, 导致工坊自定义战斗逻辑/切人优先级全部丢失(云模式下识别抖动更频繁)。
            # 改为按类名判断: 自定义类与内置类同名 -> 保留旧实例(保住工坊代码);
            # 真正换角色时类名不同 -> 仍走重建分支。
            if old_char.name != cls.__name__:
                return _apply_char_config(task, cls(task, index, char_name=info['canonical_name'],
                                                    confidence=char.confidence,
                                                    ring_index=info.get('ring_index', -1),
                                                    char_type=_get_char_type(task, info),
                                                    buff_time=_get_buff_time(task, info)), info)
            _apply_char_config(task, old_char, info)
            return old_char
    if not char:
        char = task.find_best_match_in_box(box, char_names, threshold=0.6)
        if char:
            info = char_dict.get(char.name)
            name = char.name
            cls = info.get('cls')
            return _apply_char_config(task, cls(task, index, char_name=info['canonical_name'],
                                                confidence=char.confidence,
                                                ring_index=info.get('ring_index', -1),
                                                char_type=_get_char_type(task, info),
                                                buff_time=_get_buff_time(task, info)), info)
    task.log_info(task.tr('could not find char {index} {info} {highest_confidence}').format(index=index, info=info, highest_confidence=highest_confidence))
    if old_char:
        return old_char
    if task.debug:
        task.screenshot(f'could not find char {index}')
    return BaseChar(task, index, char_name=name)


def build_char_by_canonical(task, canonical_name, index, old_char):
    """按已知 canonical 名直接构建/复用角色对象(不走画面模板匹配)。

    MuMu/安卓端编队锁定后使用: 编队里每个槽位的角色是已知的, 无需每帧
    模板匹配 —— 与 get_char_by_pos 一致, 同名类复用旧实例(保留战斗状态)。
    """
    info = char_dict.get(canonical_name)
    if not info:
        return old_char
    cls = info.get('cls')
    if old_char is not None and old_char.name == cls.__name__:
        return _apply_char_config(task, old_char, info)
    return _apply_char_config(task, cls(task, index, char_name=info['canonical_name'],
                                        confidence=1.0,
                                        ring_index=info.get('ring_index', -1),
                                        char_type=_get_char_type(task, info),
                                        buff_time=_get_buff_time(task, info)), info)


def canonical_display_name(canonical):
    """把 canonical 名(Labels 模板名)转成英文官方角色名, 用于日志显示。"""
    info = char_dict.get(canonical)
    if not info:
        return str(getattr(canonical, 'value', canonical))
    cls_name = info['cls'].__name__
    try:
        # mismatched_names 定义在 BaseCombatTask; 局部导入避免模块级循环依赖
        from src.task.BaseCombatTask import mismatched_names
        return mismatched_names.get(cls_name, cls_name)
    except Exception:
        return cls_name


def resolve_char_alias(task, token):
    """把用户输入的角色名(中文/英文/别名)解析为 canonical 名, 失败返回 None。

    canonical 名是 Labels 模板名(如 Labels.char_hiyuki, 值 'char_hiyuki')。
    匹配顺序: 类名/官方名/翻译名(中文)精确 -> 包含关系。手填编队时用户
    可以写 绯雪 / Hiyuki / 漂泊者·衍射 / Rover: Spectro 等。
    """
    token = str(token or '').strip().casefold().replace(' ', '')
    if not token:
        return None
    aliases = getattr(task, '_android_name_alias_cache', None)
    if aliases is None:
        aliases = {}
        try:
            # mismatched_names 定义在 BaseCombatTask; 局部导入避免循环依赖
            from src.task.BaseCombatTask import mismatched_names
        except Exception:
            mismatched_names = {}
        for canonical, info in char_dict.items():
            cls_name = info['cls'].__name__
            official = mismatched_names.get(cls_name, cls_name)
            names = {str(canonical), cls_name, official}
            for name in list(names):
                try:
                    translated = task.tr(name)
                    if translated and translated != name:
                        names.add(translated)
                except Exception:
                    pass
            for name in names:
                key = str(name).casefold().replace(' ', '')
                if key and key not in aliases:
                    aliases[key] = canonical
        setattr(task, '_android_name_alias_cache', aliases)
    if token in aliases:
        return aliases[token]
    for key, canonical in aliases.items():
        if len(token) >= 2 and (token in key or key in token):
            return canonical
    return None


def apply_team_char_classes(task, chars):
    """Apply custom code only after the complete three-character team is known.

    Cloud/browser capture is a compressed video stream, so a single avatar can
    fail recognition on some frames.  The old "all or nothing" behaviour meant one
    unknown avatar stripped the workshop code (and its char_type / switch priority)
    from the whole team, which showed up as "workshop parameters ignored" and
    erratic switching.  Remember the last known identity of each slot and use it
    to fill a transient gap, while still applying custom classes to the slots
    that were recognised.
    """
    if len(chars) != 3 or any(char is None for char in chars):
        return chars
    infos = [char_dict.get(char.char_name) for char in chars]

    # {index: (canonical_name, builtin_cls)} from the last fully recognised frame.
    cache = getattr(task, '_team_char_identity_cache', {}) or {}

    # Resolve each slot's identity; fall back to the cached one on a bad frame.
    identities = []
    for index, info in enumerate(infos):
        if info is not None:
            identities.append((info['canonical_name'], info['cls']))
        elif index in cache:
            identities.append(cache[index])
        else:
            identities.append(None)

    # Without a complete, distinct three-character team there is no safe team key.
    if any(identity is None for identity in identities):
        return chars
    builtin_classes = [builtin_cls for _, builtin_cls in identities]
    if len({builtin_cls.__name__ for builtin_cls in builtin_classes}) != 3:
        return chars
    try:
        team = normalize_team(builtin_classes)
    except ValueError:
        return chars

    new_cache = {}
    for index, (char, (canonical_name, builtin_cls)) in enumerate(zip(chars, identities)):
        info = infos[index]
        desired_cls = load_team_char_class(builtin_cls, team)
        if info is not None and type(char) is desired_cls:
            new_cache[index] = (canonical_name, builtin_cls)
            continue
        replacement = desired_cls(
            task,
            char.index,
            char_name=canonical_name,
            confidence=char.confidence,
            ring_index=char.ring_index,
            char_type=char.char_type,
            buff_time=char.buff_time,
        )
        replacement.__dict__.update(char.__dict__)
        # A recovered slot may carry a stale/unknown identity from the bad frame;
        # restore the resolved canonical name so later lookups keep working.
        replacement.char_name = canonical_name
        chars[index] = replacement
        new_cache[index] = (canonical_name, builtin_cls)
    task._team_char_identity_cache = new_cache
    return chars


def is_float(s):
    try:
        float(s)
        return True
    except ValueError:
        return False
