import random
import threading
import networkx as nx
import time
# ============================================================================

# GLOBAL PARAMETERS
n = [0, 1,2,3,4,5,6,7]
CAPACITY_OF_EACH_LAMBDA = 500
capacity_dict = {1: CAPACITY_OF_EACH_LAMBDA,
                 2: CAPACITY_OF_EACH_LAMBDA,
                 3: CAPACITY_OF_EACH_LAMBDA}

noOfNodes = len(n)
availableTypes = ['CS', 'pool', 'node', 'CoreCO']
typeBias = [0.4, 0, 0.6, 0]
# splitParams : [fronthaul rate(Mb), backhaul rate(Mb), max distance, frontahul latency requirement(ms), backhaul latency requirement(ms)]
splits = [0, 1, 2, 3]
splitParams = [[48, 40, 50, 2, 3], [48, 38, 50, 3, 2], [49,40, 50, 1, 2], [49,39, 50, 1, 2]]
splitBias = [0.25, 0.25, 0.25, 0.25]

BURSTS = 5
MIN_REQUESTS_IN_EACH_BURST = 5
MAX_REQUESTS_IN_EACH_BURST = 10
# ============================================================================

def assignNodeTypes(availableTypes, typeBias, noOfNodes):
    # assigning node types to each node
    nodeTypes = random.choices(availableTypes, weights=typeBias, k=noOfNodes)
    # randomly choosing one of the nodes of topology as core central office
    centralOffice = random.randint(0, len(n)-1)
    nodeTypes[centralOffice] = 'CoreCO'

    return centralOffice, nodeTypes

def assignSplit(availableSplits, splitBias, noOfNodes):
    # assigning split to each node
    chosenSplits = random.choices(availableSplits, weights=splitBias, k=noOfNodes)

    return chosenSplits

def shortestPaths(G, nodeTypes):
    # creating a dictionary of shortest paths : key = CS, value = dictionary of info about paths to all other non-CS + non-core CO nodes
    # output =  {srcNode_1 : { destNode_1 : [distance,[path]], destNode_2 : [distance,[path]] }, 
    #               srcNode_2 : { destNode_1 : [distance,[path]], destNode_2 : [distance,[path]] } } etc
    output = {}
    for source in G:  # looping over all candidate source nodes
        if nodeTypes[source] == 'CS':
            resultDictForTargetNodesOfOneSourceNode = {}
            for target in G:  # looping over all candidate target nodes
                if nodeTypes[target] != 'CoreCO' and nodeTypes[target] != 'CS':
                    try:
                        length, path = nx.single_source_dijkstra(G, source, target)
                    except nx.NetworkXNoPath:
                        pass
                    resultDictForTargetNodesOfOneSourceNode[target] = [length, path]
            output[source] =resultDictForTargetNodesOfOneSourceNode

    return output

def formatShortestPaths(dijkstraOutput):
    # fxn for formatting dictionary of shortest paths
    for source, result in dijkstraOutput.items():
        for target, path_dist in result.items():
            for dist, path in path_dist:
                print(f'Source: {source} Destination: {target} Distance: {dist} Path: {path}')

def getCellSites(typeOfEachNode):
    # returns list of nodes which are of type CS
    CS = []
    index = 0
    for nodetype in typeOfEachNode:
        if nodetype == 'CS':
            CS.append(index)
        index += 1
    
    return CS

def assignBBU(request):
    # assignBBU(request) receives request from a CS, determines whether or not a lightpath to a prospective BBU can be created, appends a 1 
    # to results list if so, and appends a 0 otherwise
    srcNode = request
    split = chosenSplits[srcNode]
    maxDistance = splitParams[split][2]
    served = False 
    path = []
    candidateBBUs = (shortestPathsDict[srcNode]).keys()
    for candidateBBu in candidateBBUs:
        distance = shortestPathsDict[srcNode][candidateBBu][0]
        path = shortestPathsDict[srcNode][candidateBBu][1]
        if(distance <= maxDistance):
            backSrc = path[-1] # for backhaul
            backDest = centralOfficeNode # for backhaul
            backwardPath = nx.single_source_dijkstra(G, backSrc, backDest)[1] # for backhaul
            lamb_f = pathMeetsFrontReq(split, path)  # returns 0(no lambda feasible), 1, 2, or 3
            lamb_b = pathMeetsBackReq(split, backwardPath)  # returns 0(no lambda feasible), 1, 2, or 3
            # when chosen BBU location satisfies distance and fronthal + backhaul reqs, construct lightpaths      
            if(lamb_f != 0 and lamb_b != 0):
                # 1) fronthaul path made 2) BBU made 3) fronthaul path teared down 4) backhaul path made 5) backhaul path teared down
                createLightpathFront(path, lamb_f, split)
                time.sleep(splitParams[split][3])
                nodeTypes[path[-1]] = 'pool' # last node on fronthaul path made BBU
                freeLightpathFront(path, lamb_f, split) 
                createLightpathBack(backwardPath, lamb_b, split)
                time.sleep(splitParams[split][4])
                freeLightpathBack(backwardPath, lamb_b, split)
                served = True # request was catered successfully
                cateredList.append(1)
    # if request was not catered successfully (either due to distance being greater than max allowed distance, 
    # or lightpath creation not being possible), append 0 to results
    if(served == False):
        cateredList.append(0)

#(path, lamb, split): "path" is list of nodes along the path, "lamb" is the wavelength to create lpath on, "split" is split option of src node
def createLightpathFront(path, lamb, split):
    # fxn to create lightpath i.e., deduct fronthaul requirement on some lambda from every link along entire path bw CS and BBU
    links = [] # list to store all the links making up the path
    # populating the links array with links in the path
    if len(path) == 2:
        links.append(G[path[0]][path[1]])
    elif len(path) == 3:
        links.append(G[path[0]][path[1]])
        links.append(G[path[1]][path[2]])
    else:
        for node in range(len(path) - 1):
            link = G[path[node]][path[node + 1]]
            links.append(link)

    i = 0
    while(i < len(links)):
         # removing the required fronthhaul req from the lightpath(lambda on each link)
        links[i]['capacity'][lamb] -= splitParams[split][0]
        i += 1

def freeLightpathFront(path, lamb, split):
    # fxn to tear down lightpath i.e., return link resource used to meet fronthaul requirement 
    links = []
    i = 0
    # populating the links array with links in the path
    if len(path) == 2:
        links.append(G[path[0]][path[1]])
    elif len(path) == 3:
        links.append(G[path[0]][path[1]])
        links.append(G[path[1]][path[2]])
    else:
        for node in range(len(path) - 1):
            link = G[path[node]][path[node + 1]]
            links.append(link)
    while(i < len(links)):
        # returning the resource used to the lightpath(lambda on each link)
        links[i]['capacity'][lamb] += splitParams[split][0]
        i += 1

def freeLightpathBack(path, lamb, split):
    # fxn to tear down lightpath i.e., return link resource used to meet backhaul requirement 
    links = []
    i = 0
    # populating the links array with links in the path
    if len(path) == 2:
        links.append(G[path[0]][path[1]])
    elif len(path) == 3:
        links.append(G[path[0]][path[1]])
        links.append(G[path[1]][path[2]])
    else:
        for node in range(len(path) - 1):
            link = G[path[node]][path[node + 1]]
            links.append(link)

    while(i < len(links)):
         # returning the resource used to the lightpath(lambda on each link)
        links[i]['capacity'][lamb] += splitParams[split][1]
        i += 1

def createLightpathBack(path, lamb, split):
    # fxn to create lightpath i.e., deduct backhaul requirement on some lambda from every link along entire path bw CS and BBU
    links = []
    i=0    
    # populating the links array with links in the path
    if len(path) == 2:
        links.append(G[path[0]][path[1]])
    elif len(path) == 3:
        links.append(G[path[0]][path[1]])
        links.append(G[path[1]][path[2]])
    else:
        for node in range(len(path) - 1):
            link = G[path[node]][path[node + 1]]
            links.append(link)

    while(i < len(links)):
        # removing the required backhaul req from the lightpath(lambda on each link)
        links[i]['capacity'][lamb] -= splitParams[split][1]
        i += 1

#(split, path): "split" is split option employed on the src node( a no.), "path" is array of nodes(no.s)
def pathMeetsFrontReq(split, path):
    # returns 0,1,2 or 3 : 1->lightpath can be created on lambda 1 along path passed into fxn,
    #                      2->lightpath can be created on lambda 2 along path passed into fxn,
    #                      3->lightpath can be created on lambda 3 along path passed into fxn
    #                      0->lightpath cannot be created on any lambda along path passed into fxn
    fronthaulReq = splitParams[split][0]
    links = []
    # populating the links array with links in the path
    if len(path) == 2:
        links.append(G[path[0]][path[1]])
    elif len(path) == 3:
        links.append(G[path[0]][path[1]])
        links.append(G[path[1]][path[2]])
    else:
        for node in range(len(path) - 1):
            link = G[path[node]][path[node + 1]]
            links.append(link)

    viableOnLamb1 = 1
    viableOnLamb2 = 1
    viableOnLamb3 = 1

    #checking if fronthaul req is met
    i = 0
    while(i < len(links)):
        
        if(links[i]['capacity'][1] < fronthaulReq):
            viableOnLamb1 = 0
            break
        i += 1
    
    if(viableOnLamb1 == 1):
        return 1

    i = 0
    while(i < len(links)):
        if(links[i]['capacity'][2] < fronthaulReq):
            viableOnLamb2 = 0
            break
        i += 1

    if(viableOnLamb2 == 1):
        return 2

    i = 0    
    while(i < len(links)):
        if(links[i]['capacity'][3] < fronthaulReq):
            viableOnLamb3 = 0
            break
        i += 1
    
    if(viableOnLamb3 == 1):
        return 3
    
    return 0


def pathMeetsBackReq(split, path):
    # returns 0,1,2 or 3 : 
    #                      1->lightpath can be created on lambda 1 along path passed into fxn,
    #                      2->lightpath can be created on lambda 2 along path passed into fxn,
    #                      3->lightpath can be created on lambda 3 along path passed into fxn
    #                      0->lightpath cannot be created on any lambda along path passed into fxn
    backhaulReq = splitParams[split][1]
    links = []  

    if len(path) == 2:
        links.append(G[path[0]][path[1]])
    elif len(path) == 3:
        links.append(G[path[0]][path[1]])
        links.append(G[path[1]][path[2]])
    else:
        for node in range(len(path) - 1):
            link = G[path[node]][path[node + 1]]
            links.append(link)

    viableOnLamb1 = 1
    viableOnLamb2 = 1
    viableOnLamb3 = 1

    #checking if backhaul req is met
    i=0
    while(i < len(links)):
        if(links[i]['capacity'][1] < backhaulReq):
            viableOnLamb1 = 0
            break
        i += 1
    
    if(viableOnLamb1 == 1):
        return 1

    i = 0
    while(i < len(links)):
        if(links[i]['capacity'][2] < backhaulReq):
            viableOnLamb2 = 0
            break
        i += 1

    if(viableOnLamb2 == 1):
        return 2

    i = 0
    while(i < len(links)):
        if(links[i]['capacity'][3] < backhaulReq):
            viableOnLamb3 = 0
            break
        i += 1
    
    if(viableOnLamb3 == 1):
        return 3
    
    return 0

def blockingRatio(results):
    total = len(results)
    zeros = 0
    for result in results:
        if result == 0:
            zeros += 1
    bp = (zeros/total) * 100
    return bp

def assignWeight():
    return random.randint(0, 10)

def changeCapacity(G, l):
    for x, y in G.edges:
        G[x][y]['capacity'][1] = l
        G[x][y]['capacity'][2] = l
        G[x][y]['capacity'][3] = l

# ====================================================================
# MAIN 
# Creating graph
G = nx.Graph()
for i in range(0, len(n)):
    G.add_node(i, pos=(random.randint(1,298),random.randint(1,298)))

G.add_edge(0,1,weight = assignWeight(), capacity = capacity_dict)
G.add_edge(0,3,weight = assignWeight(), capacity = capacity_dict)
G.add_edge(1,5,weight = assignWeight(), capacity = capacity_dict)
G.add_edge(1,6,weight = assignWeight(), capacity = capacity_dict)
G.add_edge(2,5,weight = assignWeight(), capacity = capacity_dict)
G.add_edge(2,6,weight = assignWeight(), capacity = capacity_dict)
G.add_edge(3,6,weight = assignWeight(), capacity = capacity_dict)
G.add_edge(4,5,weight = assignWeight(), capacity = capacity_dict)
G.add_edge(4,6,weight = assignWeight(), capacity = capacity_dict)
G.add_edge(5,7,weight = assignWeight(), capacity = capacity_dict)
G.add_edge(5,6,weight = assignWeight(), capacity = capacity_dict)

# Resultant list showing how many requests are blocked
cateredList = []

# assigning node types
centralOfficeNode, nodeTypes = assignNodeTypes(availableTypes, typeBias, noOfNodes)

# separating cell sites
cellSites = getCellSites(nodeTypes)

# assigning splits
chosenSplits = assignSplit(splits, splitBias, noOfNodes)

# getting shortest paths information for our topology
shortestPathsDict = shortestPaths(G, nodeTypes)

# available cell sites
CS = list(shortestPathsDict.keys())

# generating traffic
req_count = 0
threads = []
for _ in range(BURSTS):
    NO_OF_REQS_IN_EACH_BURST = random.randint(MIN_REQUESTS_IN_EACH_BURST,
                                              MAX_REQUESTS_IN_EACH_BURST)
    for i in range(NO_OF_REQS_IN_EACH_BURST):  
        print(f'Incoming request {req_count}') 
        req_count += 1
        requests = random.choices(CS, k=NO_OF_REQS_IN_EACH_BURST)   
        t = threading.Thread(target=assignBBU, args=[requests[i]])
        t.start()
        threads.append(t)
        time.sleep(random.uniform(0, 1))

for thread in threads:
    thread.join()

# printing results
print('RESULT', cateredList)
blockingRatio(cateredList)
 

# ====================================================================
# Code for generating graph of lambda vs blocking ratio
# ====================================================================

# lambdas = [100, 150, 200, 250, 300, 350, 400, 450, 500]
# r = 50
# for lam in range(len(lambdas)):
#     req_count = 0
#     changeCapacity(G, lambdas[lam])
#     print("New pass")
#     for i in range(r):  
#         print(f'Incoming request {req_count}') 
#         req_count += 1
#         requests = random.choices(CS, k=r)   
#         t = threading.Thread(target=assignBBU, args=[requests[i]])
#         t.start()
#         threads.append(t)
#         time.sleep(random.uniform(0, 1))

#     for thread in threads:
#         thread.join()

#     # printing results
#     print('RESULT', cateredList)

#     # storing results in text file
#     blocked = blockingRatio(cateredList)
#     cateredList = []

#     f = open("results.txt", "a")
#     toAppend = str(lambdas[lam]) + "\t" + str(blocked) + "\n"
#     f.write(toAppend) 
#     f.close()


# ====================================================================
# Code for generating graph of no of requests vs blocking ratio
# ====================================================================
# NO_OF_REQUESTS = [10, 15, 20, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 100]
# for i in range(len(NO_OF_REQUESTS)):
#     req_count = 0
#     r = NO_OF_REQUESTS[i]
#     print("New pass")
#     for i in range(r):  
#         print(f'Incoming request {req_count}') 
#         req_count += 1
#         requests = random.choices(CS, k=r)   
#         t = threading.Thread(target=assignBBU, args=[requests[i]])
#         t.start()
#         threads.append(t)
#         time.sleep(random.uniform(0, 1))

#     for thread in threads:
#         thread.join()

#     # printing results
#     print('RESULT', cateredList)

#     # storing results in text file
#     blocked = blockingRatio(cateredList)
#     cateredList = []

#     f = open("results.txt", "a")
#     toAppend = str(r) + "\t" + str(blocked) + "\t" + str(CAPACITY_OF_EACH_LAMBDA) + "\n"
#     f.write(toAppend) 
#     f.close()