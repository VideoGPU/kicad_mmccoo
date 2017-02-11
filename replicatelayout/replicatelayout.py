
import pcbnew

board = pcbnew.GetBoard()

# the internal coorinate space of pcbnew is 10E-6 mm. (a millionth of a mm)
# the coordinate 121550000 corresponds to 121.550000 

SCALE = 1000000.0


from collections import defaultdict
class SheetInstance:

    # "static" helper functions
    @staticmethod
    def GetSheetChildId(child):
        path = child.GetPath().split('/')
        path.pop(0) # pop the empty head
        sheetid = path[0]
        childid = "/".join(path[1:])
        return (sheetid, childid)

    @staticmethod
    def GetNetCanonical(net):
        pads = []
        for pad in net.Pads():
            sheetid, childid = SheetInstance.GetSheetChildId(pad.GetParent())
            pads.append((childid, pad.GetPadName()))
        pads.sort()

        cname = "_".join([i[0]+":"+i[1] for i in pads])
        #print("for net {} pads {}".format(net.GetNetname(), cname))
        return cname

    @staticmethod
    def NetIsSheetInternal(net):
        commonsheet = None
        #print("for net " + net.GetNetname())
        for pad in net.Pads():
            mod = pad.GetParent()
            sheetid, childid = SheetInstance.GetSheetChildId(mod)
            #print("  sheet {} child {} {}:{}".format(sheetid, str(childid), mod.GetReference(), pad.GetPadName()))
            if (childid == None):
                return None
            if commonsheet == None:
                commonsheet = sheetid
            if commonsheet != sheetid:
                return None
        return commonsheet
    
    @staticmethod
    def RegisterModulesAndNets(board):
        SheetInstance.__sheetinstances = {}
        SheetInstance.__child2sheetinstance = defaultdict(lambda: list())
        for child in board.GetModules():
            sheetid, childid = SheetInstance.GetSheetChildId(child)
            if (sheetid not in SheetInstance.__sheetinstances):
                SheetInstance.__sheetinstances[sheetid] = SheetInstance(sheetid)

            si = SheetInstance.__sheetinstances[sheetid]
            si.addChild(child)
            SheetInstance.__child2sheetinstance[childid].append(si)
        for net in board.GetNetsByNetcode().values():
            common = SheetInstance.NetIsSheetInternal(net)
            if common == None:
                continue
            si = SheetInstance.__sheetinstances[common]
            si.addInternalNet(net)
            
    @staticmethod
    def GetSheetInstanceForModule(child):
        return SheetInstance.__sheetinstances[SheetInstance.GetSheetChildId(child)[0]]

    @staticmethod
    def GetSheetInstances(child):
        sheetid, childid = SheetInstance.GetSheetChildId(child)
        return SheetInstance.__child2sheetinstance[childid]
        
    # methods
    def __init__(self, id):
        self.id = id
        self.children = {}
        self.internalnets = {}

    def __str__(self):
        retval = "sheet id is :" + self.id + " {"
        retval += ", ".join([m.GetReference() for m in self.children.values()])
        retval += "} internalnets: {"
        retval += ", ".join([n.GetNetname() for n in self.internalnets.values()])
        return retval
        
    def addChild(self, child):
        sheetid,childid = SheetInstance.GetSheetChildId(child)
        if (childid == None):
            return
        self.children[childid] = child

    def addInternalNet(self, net):
        cannon = SheetInstance.GetNetCanonical(net)
        self.internalnets[cannon] = net
        
    def getChildById(self, id):
        return self.children[id]

    def getChildCorrespondingToModule(self, child):
        sheetid, childid = SheetInstance.GetSheetChildId(child)        
        if (childid not in self.children):
            print("missing child {} others {}".format(mod.GetReference(),
                                                      ", ".join([m.GetReference()+" "+id+" "+m.GetPath() for id,m in self.children.items()])))
        return self.children[childid]

    def getChildren(self):
        return self.children.values()



    
SheetInstance.RegisterModulesAndNets(board)


# this trick came from here: http://stackoverflow.com/a/2669158
import re
tokenize = re.compile(r'(\d+)|(\D+)').findall
def natural_sortkey(string):          
    return tuple(int(num) if num else alpha for num, alpha in tokenize(string))

def replicate_sheet_trackst(fromnet, tonet, offset):
    board = tonet.GetParent()
    # remove tonet's old routing
    for track in board.TracksInNet(tonet.GetNet()):
        board.Remove(track)

    for track in board.TracksInNet(fromnet.GetNet()):
        if track.GetClass() == "VIA":
            # cloning is an easier way, but I want to ensure I
            # can create a Via from scratch
            #newvia = track.Clone()

            oldvia = board.GetViaByPosition(track.GetPosition())
            newvia = pcbnew.VIA(board)
            # need to add before SetNet will work, so just doing it first
            board.Add(newvia)
            toplayer=-1
            bottomlayer=pcbnew.LAYER_ID_COUNT
            for l in range(pcbnew.LAYER_ID_COUNT):
                if not track.IsOnLayer(l):
                    continue
                toplayer = max(toplayer, l)
                bottomlayer = min(bottomlayer, l)
            newvia.SetLayerPair(toplayer, bottomlayer)
            newvia.SetPosition(pcbnew.wxPoint(track.GetPosition().x+offset[0],
                                              track.GetPosition().y+offset[1]))
            newvia.SetViaType(oldvia.GetViaType())
            newvia.SetWidth(oldvia.GetWidth())
            newvia.SetNet(tonet)
        else:
            newtrack = pcbnew.TRACK(board)
            # need to add before SetNet will work, so just doing it first
            board.Add(newtrack)
            newtrack.SetStart(pcbnew.wxPoint(track.GetStart().x+offset[0],
                                             track.GetStart().y+offset[1]))
            newtrack.SetEnd(pcbnew.wxPoint(track.GetEnd().x+offset[0],
                                           track.GetEnd().y+offset[1]))
            newtrack.SetWidth(track.GetWidth())
            newtrack.SetLayer(track.GetLayer())

            newtrack.SetNet(tonet)


def place_instances(mainref, pitch):
    
    pitch = (pitch[0] * SCALE, pitch[1] * SCALE)
    
    pivotmod = board.FindModuleByReference(mainref)

    sheetinstance = SheetInstance.GetSheetInstanceForModule(pivotmod)
    #peers = instances[pivotsheet]

    print("getting for {}".format(pivotmod.GetReference()))
    arrayedsheets = sorted(SheetInstance.GetSheetInstances(pivotmod),
                           key = lambda elt: natural_sortkey(elt.getChildCorrespondingToModule(pivotmod).GetReference()))
    #replicasheets = sorted(children[pivotinstance], key=lambda elt: natural_sortkey(elt[2]))

    
    print("children of the same instance as {}: {}".format(mainref,
                                                           ",".join([m.GetReference() for m in sheetinstance.getChildren()])))
    
    basepositions = {}
    for mod in sheetinstance.getChildren():
        sheetid, childid = SheetInstance.GetSheetChildId(mod)
        basepositions[childid] = (mod.GetPosition().x, mod.GetPosition().y, mod.GetOrientation())

    print("basepositions {}".format(str(basepositions)))

    instnum = -1
    for i, si in enumerate(arrayedsheets):
        if (si.getChildCorrespondingToModule(pivotmod).GetReference() == mainref):
            instnum = i
            break

    print("{} is in index {}".format(mainref, instnum))

    # we start with index=-instnum because we want the pivot module to stay where it is.
    for idx, si in enumerate(arrayedsheets, start=-instnum):
        if idx == instnum:
            continue

        #first mode the modules
        for peer in si.getChildren():
            sheetid, childid = SheetInstance.GetSheetChildId(peer)
            newposition = basepositions[childid]
            newposition = (int(newposition[0] + idx*pitch[0]),
                           int(newposition[1] + idx*pitch[1]))
            
            peer.SetPosition(pcbnew.wxPoint(*newposition))
            peer.SetOrientation(basepositions[childid][2])

        #copy the nets
        for fromnetid, fromnet in sheetinstance.internalnets.items():
            if fromnetid not in si.internalnets:
                print("{} is missing from {}".format(fromnetid, ", ".join(si.internalnets.keys())))
                
            tonet = si.internalnets[fromnetid]
            print("copying net {} to {}".format(fromnet.GetNetname(), tonet.GetNetname()))
            replicate_sheet_trackst(fromnet, tonet, (idx*pitch[0],idx*pitch[1]))


            
place_instances("Q1", (10, 0))
place_instances("Q5", (10, 0))
            
