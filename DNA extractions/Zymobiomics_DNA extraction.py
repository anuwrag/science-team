def get_values(*names):
    import json
    _all_values = json.loads("""{"num_samples":8,"deepwell_type":"nest_96_wellplate_2ml_deep","res_type":"nest_12_reservoir_15ml","starting_vol":600,"binding_buffer_vol":600,"wash1_vol":500,"wash2_vol":600,"wash3_vol":600,"elution_vol":50,"mix_reps":15,"settling_time":5,"park_tips":true,"tip_track":false,"flash":false}""")
    return [_all_values[n] for n in names]


from opentrons.types import Point
import json
import os
import math
import threading
from time import sleep
from opentrons import types
import numpy as np

metadata = {
    'protocolName': 'ZymoBIOMICS™ 96 MagBead DNA Kit with Off deck Mixing',
    'author': 'Opentrons <protocols@opentrons.com>',
    'apiLevel': '2.4'
}


"""
Here is where you can modify the magnetic module engage height:
"""
#MAG_HEIGHT = 6.8 for gen2
MAG_HEIGHT = 13.6
whichwash = 1


# Definitions for deck light flashing
class CancellationToken:
    def __init__(self):
        self.is_continued = False

    def set_true(self):
        self.is_continued = True

    def set_false(self):
        self.is_continued = False


def turn_on_blinking_notification(hardware, pause):
    while pause.is_continued:
        hardware.set_lights(rails=True)
        sleep(1)
        hardware.set_lights(rails=False)
        sleep(1)


def create_thread(ctx, cancel_token):
    t1 = threading.Thread(target=turn_on_blinking_notification,
                          args=(ctx._hw_manager.hardware, cancel_token))
    t1.start()
    return t1


# Start protocol
def run(ctx):
    # Setup for flashing lights notification to empty trash
    cancellationToken = CancellationToken()

    [num_samples, deepwell_type, res_type, starting_vol, binding_buffer_vol,
     wash1_vol, wash2_vol, wash3_vol, elution_vol, mix_reps, settling_time,
     park_tips, tip_track, flash] = get_values(  # noqa: F821
        'num_samples', 'deepwell_type', 'res_type', 'starting_vol',
        'binding_buffer_vol', 'wash1_vol', 'wash2_vol', 'wash3_vol',
        'elution_vol', 'mix_reps', 'settling_time', 'park_tips', 'tip_track',
        'flash')

    """
    Here is where you can change the locations of your labware and modules
    (note that this is the recommended configuration)
    """
    magdeck = ctx.load_module('magdeck', '6')
    magdeck.disengage()
    magplate = magdeck.load_labware(deepwell_type, 'deepwell plate')
#    tempdeck = ctx.load_module('Temperature Module Gen2', '1')
    elutionplate = ctx.load_labware(
                'opentrons_96_aluminumblock_nest_wellplate_100ul',
                '2')
    waste = ctx.load_labware('nest_1_reservoir_195ml', '9',
                             'Liquid Waste').wells()[0].top()
#    res2 = ctx.load_labware(res_type, '3', 'reagent reservoir 2')
    res1 = ctx.load_labware(res_type, '3', 'reagent reservoir 1')
    num_cols = math.ceil(num_samples/8)
    tips300 = [ctx.load_labware('opentrons_96_tiprack_300ul', slot,
                                '200µl filtertiprack')
               for slot in ['1','5', '7', '8', '10', '11']]
    if park_tips:
        parkingrack = ctx.load_labware(
            'opentrons_96_tiprack_300ul', '4', 'tiprack for parking')
        parking_spots = parkingrack.rows()[0][:num_cols]
    else:
        tips300.insert(0, ctx.load_labware('opentrons_96_tiprack_300ul', '4',
                                           '200µl filtertiprack'))
        parking_spots = [None for none in range(12)]

    # load P300M pipette
    m300 = ctx.load_instrument(
        'p300_multi_gen2', 'left', tip_racks=tips300)

    """
    Here is where you can define the locations of your reagents.
    """
    binding_buffer = res1.wells()[:2]
    elution_solution = res1.wells()[-1]
    wash1 = res1.wells()[2:4]
    wash2 = res1.wells()[4:8]
    wash3 = res1.wells()[8:]

    mag_samples_m = magplate.rows()[0][:num_cols]
    elution_samples_m = elutionplate.rows()[0][:num_cols]

#    magdeck.disengage()  # just in case
#    tempdeck.set_temperature(4)

    m300.flow_rate.aspirate = 50
    m300.flow_rate.dispense = 150
    m300.flow_rate.blow_out = 300

    folder_path = '/data/B'
    tip_file_path = folder_path + '/tip_log.json'
    tip_log = {'count': {}}
    if tip_track and not ctx.is_simulating():
        if os.path.isfile(tip_file_path):
            with open(tip_file_path) as json_file:
                data = json.load(json_file)
                if 'tips300' in data:
                    tip_log['count'][m300] = data['tips300']
                else:
                    tip_log['count'][m300] = 0
        else:
            tip_log['count'][m300] = 0
    else:
        tip_log['count'] = {m300: 0}

    tip_log['tips'] = {
        m300: [tip for rack in tips300 for tip in rack.rows()[0]]}
    tip_log['max'] = {m300: len(tip_log['tips'][m300])}

    def _pick_up(pip, loc=None):
        nonlocal tip_log
        if tip_log['count'][pip] == tip_log['max'][pip] and not loc:
            ctx.pause('Replace ' + str(pip.max_volume) + 'µl tipracks before \
resuming.')
            pip.reset_tipracks()
            tip_log['count'][pip] = 0
        if loc:
            pip.pick_up_tip(loc)
            return loc
        else:
            pip.pick_up_tip(tip_log['tips'][pip][tip_log['count'][pip]])
            tip = tip_log['tips'][pip][tip_log['count'][pip]]
            tip_log['count'][pip] += 1
            return tip

    switch = True
    drop_count = 0
    # number of tips trash will accommodate before prompting user to empty
    drop_threshold = 120

    def _drop(pip):
        nonlocal switch
        nonlocal drop_count
        side = 30 if switch else -18
        drop_loc = ctx.loaded_labwares[12].wells()[0].top().move(
            Point(x=side))
        pip.drop_tip(drop_loc)
        switch = not switch
        if pip.type == 'multi':
            drop_count += 8
        else:
            drop_count += 1
        if drop_count >= drop_threshold:
            # Setup for flashing lights notification to empty trash
            if flash:
                if not ctx._hw_manager.hardware.is_simulator:
                    cancellationToken.set_true()
                thread = create_thread(ctx, cancellationToken)
            m300.home()
            ctx.pause('Please empty tips from waste before resuming.')
            ctx.home()  # home before continuing with protocol
            if flash:
                cancellationToken.set_false()  # stop light flashing after home
                thread.join()
            drop_count = 0

    waste_vol = 0
    waste_threshold = 185000

    def remove_supernatant(vol, park=False, spots=parking_spots):

        def _waste_track(vol):
            nonlocal waste_vol
            if waste_vol + vol >= waste_threshold:
                # Setup for flashing lights notification to empty liquid waste
                if flash:
                    if not ctx._hw_manager.hardware.is_simulator:
                        cancellationToken.set_true()
                    thread = create_thread(ctx, cancellationToken)
                m300.home()
                ctx.pause('Please empty liquid waste (slot 11) before \
resuming.')

                ctx.home()  # home before continuing with protocol
                if flash:
                    # stop light flashing after home
                    cancellationToken.set_false()
                    thread.join()

                waste_vol = 0
            waste_vol += vol

        m300.flow_rate.aspirate = 30
        num_trans = math.ceil(vol/200)
        vol_per_trans = vol/num_trans
        for i, (m, spot) in enumerate(zip(mag_samples_m, spots)):
            if park:
                _pick_up(m300, spot)
            else:
                _pick_up(m300)
            side = -1 if i % 2 == 0 else 1
            loc = m.bottom(0.5).move(Point(x=side*2))
            for _ in range(num_trans):
                _waste_track(vol_per_trans)
                if m300.current_volume > 0:
                    # void air gap if necessary
                    m300.dispense(m300.current_volume, m.top())
                m300.move_to(m.center())
                m300.transfer(vol_per_trans, loc, waste, new_tip='never',
                              air_gap=20)
                m300.blow_out(waste)
                m300.air_gap(20)
            _drop(m300)
        m300.flow_rate.aspirate = 150

    def resuspend_pellet(well, pip, mvol, reps=10):
        """
        'resuspend_pellet' will forcefully dispense liquid over the pellet after
        the magdeck engage in order to more thoroughly resuspend the pellet.
        param well: The current well that the resuspension will occur in.
        param pip: The pipet that is currently attached/ being used.
        param mvol: The volume that is transferred before the mixing steps.
        param reps: The number of mix repetitions that should occur. Note~
        During each mix rep, there are 2 cycles of aspirating from center,
        dispensing at the top and 2 cycles of aspirating from center,
        dispensing at the bottom (5 mixes total)
        """

        rightLeft = int(str(well).split(' ')[0][1:]) % 2
        """
        'rightLeft' will determine which value to use in the list of 'top' and
        'bottom' (below), based on the column of the 'well' used.
        In the case that an Even column is used, the first value of 'top' and
        'bottom' will be used, otherwise, the second value of each will be used.
        """
        center = well.bottom().move(types.Point(x=0,y=0,z=0.1))
        top = [
            well.bottom().move(types.Point(x=-3.8,y=3.8,z=0.1)),
            well.bottom().move(types.Point(x=3.8,y=3.8,z=0.1))
        ]
        bottom = [
            well.bottom().move(types.Point(x=-3.8,y=-3.8,z=0.1)),
            well.bottom().move(types.Point(x=3.8,y=-3.8,z=0.1))
        ]

        pip.flow_rate.dispense = 500
        pip.flow_rate.aspirate = 150

        mix_vol = 0.9 * mvol

        pip.move_to(center)
        for _ in range(reps):
            for _ in range(2):
                pip.aspirate(mix_vol, center)
                pip.dispense(mix_vol, top[rightLeft])
            for _ in range(2):
                pip.aspirate(mix_vol, center)
                pip.dispense(mix_vol, bottom[rightLeft])

    def bead_mixing(well, pip, mvol, reps=8):
        """
        'bead_mixing' will mix liquid that contains beads. This will be done by
        aspirating from the bottom of the well and dispensing from the top as to
        mix the beads with the other liquids as much as possible. Aspiration and
        dispensing will also be reversed for a short to to ensure maximal mixing.
        param well: The current well that the mixing will occur in.
        param pip: The pipet that is currently attached/ being used.
        param mvol: The volume that is transferred before the mixing steps.
        param reps: The number of mix repetitions that should occur. Note~
        During each mix rep, there are 2 cycles of aspirating from bottom,
        dispensing at the top and 2 cycles of aspirating from middle,
        dispensing at the bottom
        """
        #Set for Nest 2 ml Deepwell
        center = well.top().move(types.Point(x=0,y=0,z=5))
        aspbot = well.bottom(1)
        asptop = well.bottom(10)
        disbot = well.bottom(3)
        distop = well.top()

        vol = mvol * .9

        pip.move_to(center)
        for _ in range(reps):
            pip.aspirate(vol,aspbot)
            pip.dispense(vol,distop)
            pip.aspirate(vol,asptop)
            pip.dispense(vol,disbot)


    def bind(vol, park=True):
        latest_chan = -1
        tips = []
        for i, well in enumerate(mag_samples_m):
            tip = _pick_up(m300)
            tips.append(tip)
            num_trans = math.ceil(vol/200)
            vol_per_trans = vol/num_trans
            asp_per_chan = (0.95*res1.wells()[0].max_volume)//(vol_per_trans*8)
            for t in range(num_trans):
                chan_ind = i//(12//len(binding_buffer))
                source = binding_buffer[chan_ind]
                if m300.current_volume > 0:
                    # void air gap if necessary
                    m300.dispense(m300.current_volume, source.top())
                if chan_ind > latest_chan:  # mix if accessing new channel
                    bead_mixing(source,m300,200,reps=6)
                    latest_chan = chan_ind
                m300.transfer(vol_per_trans, source, well.top(), air_gap=20,
                              new_tip='never')
                if t < num_trans - 1:
                    m300.air_gap(20)
            bead_mixing(well,m300,200,reps=6)
            m300.blow_out(well.top(-2))
            m300.air_gap(20)

            if park:
                m300.drop_tip(tip)
            else:
                _drop(m300)


        BindIncubate = 5
        for binddelay in np.arange(BindIncubate, 0, -1): #Bind delay countdown- (BindIncubate * 2) minutes long
            ctx.delay(minutes=2, msg='Take plate off magdeck and vortex for 10 - 15 seconds.')

        magdeck.engage(height=MAG_HEIGHT)
        for bindi in np.arange(settling_time,0,-0.5): #Settling time delay with countdown timer
            ctx.delay(minutes=0.5, msg='There are ' + str(bindi) + ' minutes left in the incubation.')

        # remove initial supernatant
        remove_supernatant(vol+starting_vol, park=park, spots=tips)

    def wash(vol, source, mix_reps=15, park=True, resuspend=True):

        global whichwash #Defines which wash the protocol is on to log on the app

        if source == wash1:
            whichwash = 1
        if source == wash2:
            whichwash = 2
        if source == wash3:
            whichwash = 3
        else:
            whichwash = whichwash+1

        if resuspend and magdeck.status == 'engaged':
            magdeck.disengage()

        num_trans = math.ceil(vol/200)
        vol_per_trans = vol/num_trans
        for i, (m, spot) in enumerate(zip(mag_samples_m, parking_spots)):
            _pick_up(m300)
            side = 1 if i % 2 == 0 else -1
            loc = m.bottom(0.5).move(Point(x=side*2))
            src = source[i//(12//len(source))]
            for n in range(num_trans):
                if m300.current_volume > 0:
                    m300.dispense(m300.current_volume, src.top())
                m300.transfer(vol_per_trans, src, m.top(), air_gap=20,
                              new_tip='never')
                if n < num_trans - 1:  # only air_gap if going back to source
                    m300.air_gap(20)
            if resuspend:
                #m300.mix(mix_reps, 150, loc)
                resuspend_pellet(m, m300, 180)

            m300.blow_out(m.top())
            m300.air_gap(20)
            if park:
                m300.drop_tip(spot)
            else:
                _drop(m300)

        if magdeck.status == 'disengaged':
            magdeck.engage(height=MAG_HEIGHT)

        for washi in np.arange(settling_time,0,-0.5): #settling time timer for washes
            ctx.delay(minutes=0.5, msg='There are ' + str(washi) + ' minutes left in wash ' + str(whichwash) + ' incubation.')

        remove_supernatant(vol, park=park)


    def elute(vol, park=True):

        # resuspend beads in elution
        if magdeck.status == 'enagaged':
            magdeck.disengage()
        for i, (m, spot) in enumerate(zip(mag_samples_m, parking_spots)):
            _pick_up(m300)
            side = 1 if i % 2 == 0 else -1
            loc = m.bottom(0.5).move(Point(x=side*2))
            m300.aspirate(vol, elution_solution)
            m300.move_to(m.center())
            m300.dispense(vol, loc)
            resuspend_pellet(m, m300, 50, reps=4)
            m300.blow_out(m.bottom(5))
            m300.air_gap(20)
            if park:
                m300.drop_tip(spot)
            else:
                _drop(m300)

        elutedelay = 5 #Creates a delay for elution that is elutedelay minutes long
        for elutebind in np.arange(elutedelay,0,-0.5):
            ctx.delay(minutes=0.5, msg='There are ' + str(elutebind) + ' minutes left in the elution attachment step.')
        magdeck.engage(height=MAG_HEIGHT)

        for elutei in np.arange(settling_time,0,-0.5): #settling time countdown
            ctx.delay(minutes=0.5, msg='There are ' + str(elutei) + ' minutes left in the elution incubation.')

        for i, (m, e, spot) in enumerate(
                zip(mag_samples_m, elution_samples_m, parking_spots)):
            if park:
                _pick_up(m300, spot)
            else:
                _pick_up(m300)
            side = -1 if i % 2 == 0 else 1
            loc = m.bottom(0.5).move(Point(x=side*2))
            m300.transfer(vol, loc, e.bottom(5), air_gap=20, new_tip='never')
            m300.blow_out(e.top(-2))
            m300.air_gap(20)
            m300.drop_tip()

    """
    Here is where you can call the methods defined above to fit your specific
    protocol. The normal sequence is:
    """
    bind(binding_buffer_vol, park=True)
    wash(wash1_vol, wash1, park=False, resuspend=True)
    wash(wash2_vol, wash2, park=False, resuspend=True)
    wash(wash3_vol, wash3, park=False, resuspend=True)
    drybeads = 5 #Number of minutes you want to dry for
    for beaddry in np.arange(drybeads,0,-0.5):
        ctx.delay(minutes=0.5, msg='There are ' + str(beaddry) + ' minutes left in the drying step.')
    elute(elution_vol, park=False)

    # track final used tip
    if tip_track and not ctx.is_simulating():
        if not os.path.isdir(folder_path):
            os.mkdir(folder_path)
        data = {'tips300': tip_log['count'][m300]}
        with open(tip_file_path, 'w') as outfile:
            json.dump(data, outfile)
