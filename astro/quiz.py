# -*- coding: utf-8 -*-
"""Post-mission quiz and suggested assistant questions.

Both adapt to the player's age group: wording, difficulty and depth change for young (6-9), mid (10-13)
and teen (14+).  Quiz format:  QUIZ[mission_id] -> [ {age: {lang: (question, [options], correct_index, explanation)}} ]
"""
import random
from typing import Dict, List, Tuple

AGES = ("young", "mid", "teen")


def _q(young, mid, teen):
    return {"young": young, "mid": mid, "teen": teen}


QUIZ: Dict[str, List[dict]] = {
    "moon": [
        _q({"en": ("Why is Moon dust so sharp?", ["Nothing on the Moon smooths it down", "It is made of tiny needles from Earth", "Because it rains a lot"], 0,
                   "There is no wind or rain on the Moon, so the sharp grains never get rubbed smooth."),
            "ar": ("لماذا غبار القمر حادّ جدًّا؟", ["لأنه لا شيء على القمر يُنعّمه", "لأنه إبر صغيرة جاءت من الأرض", "لأن المطر ينزل كثيرًا"], 0,
                   "لا رياح ولا مطر على القمر، فلا تُنعَّم الحبيبات الحادّة أبدًا.")},
           {"en": ("Why does lunar dust stay sharp and jagged?", ["Earth's gravity sharpens it", "There is no wind or water to wear the grains smooth", "It is made of metal"], 1,
                   "Without weather the grains made by meteoroid impacts are never eroded."),
            "ar": ("لماذا يبقى غبار القمر حادًّا وخشنًا؟", ["جاذبية الأرض تُحدّده", "لا رياح ولا ماء لتنعيم الحبيبات", "لأنه مصنوع من المعدن"], 1,
                   "بلا طقس لا تتآكل الحبيبات التي صنعتها اصطدامات النيازك.")},
           {"en": ("What made most lunar regolith, and why does it stay angular?", ["Volcanoes; solar wind polishes it", "Billions of years of impacts; no air or water erodes it", "Moonquakes; tides round it off"], 1,
                   "Impact gardening shatters rock, and with no atmosphere or liquid water the fragments are never rounded."),
            "ar": ("ما الذي صنع معظم الريغوليث القمري، ولماذا يبقى زاويًّا؟", ["البراكين؛ والرياح الشمسية تصقله", "مليارات السنين من الاصطدامات؛ ولا هواء ولا ماء يُبليه", "الزلازل القمرية؛ والمدّ يستدير به"], 1,
                   "تحطّم الاصطدامات الصخر، وبلا غلاف جوي أو ماء سائل لا تستدير الشظايا.")}),
        _q({"en": ("At night on the Moon it gets...", ["very warm", "freezing cold", "rainy"], 1,
                   "With no air to keep heat in, the Moon gets freezing cold at night."),
            "ar": ("في ليل القمر يصير الجوّ...", ["دافئًا جدًّا", "شديد البرودة", "ماطرًا"], 1,
                   "بلا هواء يحفظ الحرارة، يصير القمر شديد البرودة ليلًا.")},
           {"en": ("Why does the Moon swing between very hot and very cold?", ["It has no atmosphere to hold or carry heat", "It is closer to the Sun at night", "Its dust makes cold"], 0,
                   "Air spreads and stores heat on Earth; the Moon has almost none."),
            "ar": ("لماذا يتأرجح القمر بين الحرّ الشديد والبرد الشديد؟", ["ليس له غلاف جوي يحفظ الحرارة أو ينقلها", "لأنه أقرب إلى الشمس ليلًا", "لأن غباره يصنع البرودة"], 0,
                   "الهواء على الأرض ينشر الحرارة ويخزّنها، وهو شبه معدوم على القمر.")},
           {"en": ("About how big is the Moon's day-night surface temperature swing?", ["About 20 °C", "About 250 °C", "About 1000 °C"], 1,
                   "From roughly +100 °C in sunlight to about -150 °C or colder at night."),
            "ar": ("كم يبلغ تقريبًا تأرجح حرارة سطح القمر بين النهار والليل؟", ["نحو 20 °م", "نحو 250 °م", "نحو 1000 °م"], 1,
                   "من نحو +100 °م في الشمس إلى نحو -150 °م أو أقل ليلًا.")}),
    ],
    "mars": [
        _q({"en": ("Which clue shows that Mars once had water?", ["Round smooth pebbles", "Its red color", "Its craters"], 0,
                   "Water rolls pebbles until they are round and smooth."),
            "ar": ("أي دليل يُظهر أن المريخ كان فيه ماء؟", ["الحصى المستدير الأملس", "لونه الأحمر", "حفره"], 0,
                   "الماء يُدحرج الحصى حتى يصير مستديرًا أملس.")},
           {"en": ("What does finding clay on Mars suggest?", ["It was always dry", "Rock sat in liquid water for a long time", "Wind made it recently"], 1,
                   "Clay minerals form when rock and liquid water interact for a long time."),
            "ar": ("ماذا يوحي وجود الطين على المريخ؟", ["أنه كان جافًّا دائمًا", "أن الصخر بقي في ماء سائل زمنًا طويلًا", "أن الرياح صنعته حديثًا"], 1,
                   "تتكوّن المعادن الطينية حين يتفاعل الصخر مع الماء السائل زمنًا طويلًا.")},
           {"en": ("Why are Jezero's delta clays prime sample targets?", ["They are the youngest rocks", "They formed in water and can preserve organic molecules", "They are easiest to reach"], 1,
                   "Clay-rich delta sediments are good at trapping and preserving organic material."),
            "ar": ("لماذا تُعدّ طين دلتا جيزيرو هدفًا مهمًّا للعيّنات؟", ["لأنها أحدث الصخور", "لأنها تكوّنت في الماء وقد تحفظ جزيئات عضوية", "لأنها الأسهل وصولًا"], 1,
                   "الرواسب الطينية في الدلتا جيدة في حبس المواد العضوية وحفظها.")}),
        _q({"en": ("Can we wash the rover with water on Mars?", ["Yes, water is everywhere", "No, water freezes or disappears there", "Yes, but only on Mondays"], 1,
                   "Mars is too cold and its air too thin for water to stay liquid."),
            "ar": ("هل نستطيع غسل المركبة بالماء على المريخ؟", ["نعم، الماء في كل مكان", "لا، الماء يتجمّد أو يختفي هناك", "نعم، لكن يوم الاثنين فقط"], 1,
                   "المريخ بارد جدًّا وهواؤه رقيق، فلا يبقى الماء سائلًا.")},
           {"en": ("Why can't liquid water stay on Mars's surface today?", ["The air is too thin and cold", "There is too much gravity", "The Sun is too close"], 0,
                   "Low pressure and low temperature make water freeze or evaporate."),
            "ar": ("لماذا لا يبقى الماء السائل على سطح المريخ اليوم؟", ["الهواء رقيق وبارد جدًّا", "الجاذبية كبيرة جدًّا", "الشمس قريبة جدًّا"], 0,
                   "الضغط المنخفض والحرارة المنخفضة يجعلان الماء يتجمّد أو يتبخّر.")},
           {"en": ("Mars's atmosphere is about what fraction as thick as Earth's, and mostly which gas?", ["About 1%, mostly carbon dioxide", "About 50%, mostly oxygen", "About 10%, mostly nitrogen"], 0,
                   "It is roughly one percent as thick and about 95% carbon dioxide."),
            "ar": ("ما سُمك غلاف المريخ الجوي نسبةً إلى الأرض، وما غازه الغالب؟", ["نحو 1%، ومعظمه ثاني أكسيد الكربون", "نحو 50%، ومعظمه أكسجين", "نحو 10%، ومعظمه نيتروجين"], 0,
                   "هو نحو واحد بالمئة من سُمك غلاف الأرض، ونحو 95% منه ثاني أكسيد الكربون.")}),
    ],
    "orbital": [
        _q({"en": ("Why do astronauts float in the space station?", ["There is no gravity there", "They keep falling around the Earth with their ship", "The air pushes them up"], 1,
                   "Gravity is still there! They and the station fall around the Earth together."),
            "ar": ("لماذا يطفو الرواد في محطة الفضاء؟", ["لا توجد جاذبية هناك", "لأنهم يسقطون حول الأرض مع مركبتهم", "لأن الهواء يدفعهم للأعلى"], 1,
                   "الجاذبية موجودة! هم والمحطة يسقطون حول الأرض معًا.")},
           {"en": ("Why do astronauts on the ISS float?", ["Gravity is zero at that height", "They are in continuous free fall around Earth", "The station's engines cancel gravity"], 1,
                   "Free fall around Earth feels like weightlessness."),
            "ar": ("لماذا يطفو رواد المحطة الدولية؟", ["الجاذبية صفر على ذلك الارتفاع", "لأنهم في سقوط حر مستمر حول الأرض", "محرّكات المحطة تُلغي الجاذبية"], 1,
                   "السقوط الحر حول الأرض يعطي إحساس انعدام الوزن.")},
           {"en": ("At the ISS's altitude, gravity is about what fraction of surface gravity?", ["About 10%", "About 90%", "Zero"], 1,
                   "The station is only ~400 km up, so gravity is still about 90% as strong."),
            "ar": ("على ارتفاع المحطة الدولية، تبلغ الجاذبية تقريبًا كم من جاذبية السطح؟", ["نحو 10%", "نحو 90%", "صفر"], 1,
                   "المحطة على ارتفاع نحو 400 كم فقط، فالجاذبية نحو 90% من قوّتها.")}),
        _q({"en": ("What does the air cleaner catch?", ["The gas we breathe out", "Little stars", "Dust bunnies only"], 0,
                   "It catches carbon dioxide, the gas we breathe out."),
            "ar": ("ماذا يلتقط منظّف الهواء؟", ["الغاز الذي نزفره", "نجومًا صغيرة", "غبارًا فقط"], 0,
                   "يلتقط ثاني أكسيد الكربون، وهو الغاز الذي نزفره.")},
           {"en": ("What does a CO2 scrubber do?", ["Adds oxygen only", "Captures the carbon dioxide the crew exhales", "Cools the cabin"], 1,
                   "Scrubbers remove CO2 so it does not build up to harmful levels."),
            "ar": ("ماذا يفعل منقّي ثاني أكسيد الكربون؟", ["يضيف الأكسجين فقط", "يلتقط ثاني أكسيد الكربون الذي يزفره الطاقم", "يبرّد المقصورة"], 1,
                   "تُزيل المنقّيات الغاز كي لا يتراكم إلى مستويات ضارّة.")},
           {"en": ("Why are fans essential for life support in microgravity?", ["No convection: exhaled CO2 would pool around people", "They make artificial gravity", "They cool the engines"], 0,
                   "Without convection, a still pocket of CO2 can form around a sleeping astronaut's face."),
            "ar": ("لماذا المراوح ضرورية لدعم الحياة في الجاذبية الصغرى؟", ["لا حمل حراري: فيتجمّع الغاز المزفور حول الأشخاص", "لأنها تصنع جاذبية صناعية", "لأنها تبرّد المحرّكات"], 0,
                   "بلا حمل حراري قد تتكوّن جيب ساكن من الغاز حول وجه رائد نائم.")}),
    ],
    "europa": [
        _q({"en": ("What is hiding under Europa's ice?", ["A giant salty ocean", "A chocolate volcano", "Nothing at all"], 0,
                   "Scientists think a huge salty ocean lies under the ice."),
            "ar": ("ماذا يختبئ تحت جليد أوروبا؟", ["محيط مالح عملاق", "بركان من الشوكولاتة", "لا شيء إطلاقًا"], 0,
                   "يظنّ العلماء أن محيطًا مالحًا ضخمًا يقع تحت الجليد.")},
           {"en": ("What warms the inside of Europa?", ["Jupiter's gravity squeezing and stretching it", "A giant campfire", "Moonlight"], 0,
                   "This tidal flexing makes heat inside the moon."),
            "ar": ("ما الذي يُدفّئ داخل أوروبا؟", ["جاذبية المشتري التي تضغطه وتشدّه", "نار مخيّم عملاقة", "ضوء القمر"], 0,
                   "هذا الانثناء المدّي يولّد حرارة داخل القمر.")},
           {"en": ("What drives tidal heating on Europa?", ["Flexing from its slightly elliptical, resonant orbit", "Radioactive ice", "Sunlight absorbed by the shell"], 0,
                   "Varying tidal stress from an eccentric orbit flexes the interior and dissipates heat."),
            "ar": ("ما مصدر التسخين المدّي في أوروبا؟", ["انثناء بسبب مداره البيضاوي الرنيني", "جليد مشعّ", "ضوء الشمس الذي تمتصّه القشرة"], 0,
                   "تتغيّر إجهادات المدّ بسبب المدار اللامركزي فتثني الداخل وتبدّد الحرارة.")}),
        _q({"en": ("Why do we warm the drill tip first?", ["The ice is as hard as a rock", "To make it shiny", "Because it is bored"], 0,
                   "At about -160 °C ice is rock-hard, so a warm tip works gently."),
            "ar": ("لماذا نسخّن رأس المثقاب أولًا؟", ["لأن الجليد صلب كالصخر", "ليصير لامعًا", "لأنه يشعر بالملل"], 0,
                   "عند نحو -160 °م يصير الجليد صلبًا كالصخر، فالرأس الدافئ يعمل بلطف.")},
           {"en": ("Why heat the drill tip before drilling?", ["Heat softens the contact ice and avoids snapping the bit", "Heat makes the drill spin faster", "Heat attracts the ocean"], 0,
                   "Softening the contact ice reduces the force needed."),
            "ar": ("لماذا نسخّن رأس المثقاب قبل الحفر؟", ["الحرارة تلين الجليد الملامس وتمنع انكسار المثقاب", "الحرارة تجعله يدور أسرع", "الحرارة تجذب المحيط"], 0,
                   "تلين الجليد الملامس فتقلّ القوة اللازمة.")},
           {"en": ("Why is sunlight a poor heat source at Europa?", ["At Jupiter's distance it is only ~4% as strong as at Earth", "Europa is shaded by Mars", "Ice reflects all of it"], 0,
                   "Sunlight weakens with the square of distance; Jupiter is about 5 times farther from the Sun."),
            "ar": ("لماذا ضوء الشمس مصدر حرارة ضعيف عند أوروبا؟", ["عند بُعد المشتري لا يتجاوز نحو 4% من قوّته على الأرض", "لأن المريخ يظلّل أوروبا", "لأن الجليد يعكسه كله"], 0,
                   "يضعف ضوء الشمس بمربّع المسافة، والمشتري أبعد بنحو 5 مرات.")}),
    ],
}


def quiz_for(mission_id: str, age: str, lang: str, seed=None) -> List[Tuple[str, List[str], int, str]]:
    """Return the quiz for a mission, adapted to age/language, with options shuffled (answer index remapped)."""
    rng = random.Random(seed)
    out = []
    for item in QUIZ[mission_id]:
        q, opts, correct, expl = item[age][lang]
        order = list(range(len(opts)))
        rng.shuffle(order)
        out.append((q, [opts[i] for i in order], order.index(correct), expl))
    return out


# Suggested questions for the assistant panel (tap to ask) -> [mission][age][lang]
SUGGESTED: Dict[str, Dict[str, Dict[str, List[str]]]] = {
    "moon": {
        "young": {"en": ["Why is the Moon so hot and cold?", "What is Moon dust?", "Can we breathe on the Moon?"],
                  "ar": ["لماذا القمر حارّ وبارد جدًّا؟", "ما هو غبار القمر؟", "هل نستطيع التنفّس على القمر؟"]},
        "mid": {"en": ["Why does the Moon have no wind?", "What is regolith made of?", "Why do solar panels need batteries on the Moon?"],
                "ar": ["لماذا لا توجد رياح على القمر؟", "مم يتكوّن الريغوليث؟", "لماذا تحتاج الألواح الشمسية إلى بطاريات على القمر؟"]},
        "teen": {"en": ["How big is the Moon's day-night temperature swing and why?", "Why does lunar dust cling to suits?", "How long is a lunar night and how do outposts survive it?"],
                 "ar": ["كم يبلغ تأرجح حرارة القمر بين النهار والليل ولماذا؟", "لماذا يلتصق غبار القمر بالبدلات؟", "كم يطول ليل القمر وكيف تنجو القواعد منه؟"]}},
    "mars": {
        "young": {"en": ["Was there water on Mars?", "Why is Mars red?", "Can I jump high on Mars?"],
                  "ar": ["هل كان على المريخ ماء؟", "لماذا المريخ أحمر؟", "هل أقفز عاليًا على المريخ؟"]},
        "mid": {"en": ["What does clay tell us about Mars?", "Why can't water stay liquid on Mars?", "How does dust affect rovers?"],
                "ar": ["ماذا يخبرنا الطين عن المريخ؟", "لماذا لا يبقى الماء سائلًا على المريخ؟", "كيف يؤثّر الغبار على المركبات الجوّالة؟"]},
        "teen": {"en": ["Why are clay minerals good places to look for ancient life?", "How thin is Mars's atmosphere compared to Earth's?", "How do wind gusts clean rover panels?"],
                 "ar": ["لماذا تُعدّ المعادن الطينية أماكن جيدة للبحث عن حياة قديمة؟", "ما مدى رقّة غلاف المريخ مقارنةً بالأرض؟", "كيف تنظّف هبّات الريح ألواح المركبات؟"]}},
    "orbital": {
        "young": {"en": ["Why do astronauts float?", "How do plants grow in space?", "What is carbon dioxide?"],
                  "ar": ["لماذا يطفو رواد الفضاء؟", "كيف تنمو النباتات في الفضاء؟", "ما هو ثاني أكسيد الكربون؟"]},
        "mid": {"en": ["Is there gravity on the space station?", "Why do plants need light in orbit?", "How does a CO2 scrubber work?"],
                "ar": ["هل توجد جاذبية في محطة الفضاء؟", "لماذا تحتاج النباتات إلى الضوء في المدار؟", "كيف يعمل منقّي ثاني أكسيد الكربون؟"]},
        "teen": {"en": ["How does free fall create an orbit?", "Why does CO2 pool around sleeping astronauts?", "How do plants orient themselves without gravity?"],
                 "ar": ["كيف يصنع السقوط الحر مدارًا؟", "لماذا يتجمّع ثاني أكسيد الكربون حول الرواد النائمين؟", "كيف تتوجّه النباتات بلا جاذبية؟"]}},
    "europa": {
        "young": {"en": ["What is Europa?", "Is there an ocean under the ice?", "Why is it so cold on Europa?"],
                  "ar": ["ما هو أوروبا؟", "هل يوجد محيط تحت الجليد؟", "لماذا البرد شديد على أوروبا؟"]},
        "mid": {"en": ["What is tidal heating?", "How do we know Europa might have an ocean?", "Why is Europa a good place to look for life?"],
                "ar": ["ما هو التسخين المدّي؟", "كيف نعرف أن أوروبا قد يكون فيه محيط؟", "لماذا أوروبا مكان جيد للبحث عن الحياة؟"]},
        "teen": {"en": ["How does Europa's orbit create tidal heating?", "How could a spacecraft sample the ocean?", "How cold is Europa and what does that do to ice?"],
                 "ar": ["كيف يصنع مدار أوروبا تسخينًا مدّيًّا؟", "كيف يمكن لمركبة أخذ عيّنات من المحيط؟", "ما مدى برودة أوروبا وماذا يفعل ذلك بالجليد؟"]}},
}
