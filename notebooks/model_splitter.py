import numpy as np
import flopy
import pandas as pd
from flopy.mf6.mfbase import PackageContainer
import matplotlib.pyplot as plt
import inspect


OBS_ID1_LUT = {
    "gwf": "cellid",
    "csub": {
        "csub": "icsubno",
        "ineslastic-csub": "icsubno",
        "elastic-csub": "icsubno",
        "coarse-csub": "cellid",
        "csub-cell": "cellid",
        "wcomp-csub-cell": "cellid",
        "sk": "icsubno",
        "ske": "icsubno",
        "sk-cell": "cellid",
        "ske-cell": "cellid",
        "estress-cell": "cellid",
        "gstress-cell": "cellid",
        "interbed-compaction": "icsubno",
        "inelastic-compaction": "icsubno",
        "elastic-compaction": "icsubno",
        "coarse-compaction": "cellid",
        "inelastic-compaction-cell": "cellid",
        "elastic-compaction-cell": "cellid",
        "compaction-cell": "cellid",
        "thickness": "icsubno",
        "coarse-thickness": "cellid",
        "thickness-cell": "cellid",
        "theta": "icsubno",
        "coarse-theta": "cellid",
        "theta-cell": "cellid",
        "delay-flowtop": "icsubno",
        "delay-flowbot": "icsubno",
        "delay-head": "icsubno",
        "delay-gstress": "icsubno",
        "delay-estress": "icsubno",
        "delay-preconstress": "icsubno",
        "delay-compaction": "icsubno",
        "delay-thickness": "icsubno",
        "delay-theta": "icsubno",
        "preconstress-cell": "cellid",
    },
    "chd": "cellid",
    "drn": "cellid",
    "evt": "cellid",
    "ghb": "cellid",
    "rch": "cellid",
    "riv": "cellid",
    "wel": "cellid",
    "lak": {
        "stage": "lakeno",
        "ext-inflow": "lakeno",
        "outlet-inflow": "lakeno",
        "inflow": "lakeno",
        "from-mvr": "lakeno",
        "rainfall": "lakeno",
        "runoff": "lakeno",
        "lak": "lakeno",
        "withdrawal": "lakeno",
        "evaporation": "lakeno",
        "ext-outflow": "lakeno",
        "to-mvr": "outletno",
        "storage": "lakeno",
        "constant": "lakeno",
        "outlet": "outletno",
        "volume": "lakeno",
        "surface-area": "lakeno",
        "wetted-area": "lakeno",
        "conductance": "lakeno"
    },
    "maw": "wellno",
    "sfr": "rno",
    "uzf": "iuzno",
    # transport
    "gwt": "cellid",
    "cnc": "cellid",
    "src": "cellid",
    "sft": "rno",
    "lkt": "lakeno",
    "mwt": "mawno",
    "uzt": "uztno"
}

OBS_ID2_LUT = {
    "gwf": "cellid",
    "csub": "icsubno",
    "chd": None,
    "drn": None,
    "evt": None,
    "ghb": None,
    "rch": None,
    "riv": None,
    "wel": None,
    "sfr": None,
    "lak": None,
    "maw": None,
    "uzf": None,
    "gwt": "cellid",
    "cnc": None,
    "src": None,
    "sft": "rno",
    "lkt": {
        "flow-ja-face": "lakeno",
        "lkt": None,
    },
    "mwt": None,
    "uzt": "uztno"
}


class Mf6Splitter(object):
    """
    A class for splitting a single model into a multi-model simulation

    Parameters
    ----------
    sim : flopy.mf6.MFSimulation
    modelname : str, None
        name of model to split
    """
    def __init__(self, sim, modelname=None):
        self._sim = sim
        self._model = self._sim.get_model(modelname)
        if modelname is None:
            self._modelname = self._model.name
        self._model_type = self._model.model_type
        if self._model_type.endswith("6"):
            self._model_type = self._model_type[:-1]
        self._modelgrid = self._model.modelgrid
        self._node_map = {}
        self._new_connections = None
        self._new_ncpl = None
        self._grid_info = None
        self._exchange_metadata = None
        self._connection = None
        self._uconnection = None
        self._usg_metadata = None
        self._connection_ivert = None
        self._model_dict = None
        self._ivert_vert_remap = None
        self._sfr_mover_connections = []
        self._mover = False
        self._pkg_mover = False
        self._pkg_mover_name = None
        self._mover_remaps = {}
        self._sim_mover_data = {}
        self._new_sim = None
        self._offsets = {}
        # dictionaries of remaps necessary for piping GWF info to GWT
        self._uzf_remaps = {}
        self._lak_remaps = {}
        self._sfr_remaps = {}
        self._maw_remaps = {}

    @property
    def new_simulation(self):
        """
        Returns the new simulation object after model splitting
        """
        return self._new_sim

    def switch_models(self, modelname, remap_nodes=False):
        """
        Method to switch which model within a simulation that is being split.
        Models must be congruent. Ex. GWF model followed by a GWT model.
        If the models are not congruent remap_nodes must be set to True.

        Parameters
        ----------
        modelname : str
            model name to switch to
        remap_nodes : bool
            boolean flag to force the class to remap the node look up table.
            This is used when models do not overlap (ex. two seperate
            GWF models). Excahanges between original models are not preserved
            currently.

        Returns
        -------
        None
        """
        self._model = self._sim.get_model(modelname)
        self._modelname = self._model.name
        self._model_type = self._model.model_type
        if self._model_type.endswith("6"):
            self._model_type = self._model_type[:-1]

        self._model_dict = None

        if remap_nodes:
            self._modelgrid = self._model.modelgrid
            self._node_map = {}
            self._new_connections = None
            self._new_ncpl = None
            self._grid_info = None
            self._exchange_metadata = None
            self._connection = None
            self._uconnection = None
            self._usg_metadata = None
            self._connection_ivert = None
            self._ivert_vert_remap = None
            self._sfr_mover_connections = []
            self._mover = False
            self._pkg_mover = False
            self._pkg_mover_name = None
            self._mover_remaps = {}
            self._sim_mover_data = {}
            self._offsets = {}

    @property
    def original_modelgrid(self):
        """
        Method to return the original model's modelgrid object. This is
        used for re-assembling the split models when analyzing output

        """
        return self._modelgrid

    def reconstruct_array(self, arrays):
        """
        Method to reconstruct model output arrays into a single array
        with the dimensions of the original model

        arrays : dict
            dictionary of model number and the associated array

        Returns
        -------
            np.ndarray of original model shape
        """


        arr = np.zeros(self._modelgrid.shape)


        return

    def _remap_nodes(self, array):
        """
        Method to remap existing nodes to new models

        Parameters
        ----------
        array : numpy array
            numpy array of dimension ncpl (nnodes for DISU models)

        """
        array = np.ravel(array)

        if self._modelgrid.iverts is None:
            self._map_iac_ja_connections()
        else:
             self._map_connections()

        grid_info = {}
        if self._modelgrid.grid_type == "structured":
            a = array.reshape(self._modelgrid.nrow, self._modelgrid.ncol)
            for m in np.unique(a):
                cells = np.where(a == m)
                rmin, rmax = np.min(cells[0]), np.max(cells[0])
                cmin, cmax = np.min(cells[1]), np.max(cells[1])
                cells = list(zip(cells[0], cells[1]))
                self._offsets[m] = {
                    "xorigin": self._modelgrid.xvertices[rmax + 1, cmin],
                    "yorigin": self._modelgrid.yvertices[rmax + 1, cmin]
                }
                # get new nrow and ncol information
                nrow = (rmax - rmin) + 1
                ncol = (cmax - cmin) + 1
                mapping = np.ones((nrow, ncol), dtype=int) * -1
                for ix, oix in enumerate(range(rmin, rmax + 1)):
                    for jx, jix in enumerate(range(cmin, cmax + 1)):
                        if (oix, jix) in cells:
                            onode = self._modelgrid.get_node((0, oix, jix))[0]
                            mapping[ix, jx] = onode
                grid_info[m] = [(nrow, ncol), (rmin, rmax), (cmin, cmax),
                                np.ravel(mapping)]
        else:
            xverts, yverts = self._irregular_shape_patch(
                self._modelgrid.xvertices,
                self._modelgrid.yvertices
            )
            for m in np.unique(array):
                cells = np.where(array == m)
                grid_info[m] = [(len(cells[0]),), None, None, None]

                # calculate grid offsets
                if xverts is not None:
                    mxv = xverts[cells[0]]
                    myv = yverts[cells[0]]
                    xmidx = np.where(mxv == np.nanmin(mxv))[0]
                    myv = myv[xmidx]
                    ymidx = np.where(myv == np.nanmin(myv))[0]

                    self._offsets[m] = {
                        "xorigin": np.nanmin(mxv[xmidx[0]]),
                        "yorigin": np.nanmin(myv[ymidx][0])
                    }
                else:
                    self._offsets[m] = {"xorigin": None, "yorigin": None}

        new_ncpl = {}
        for m in np.unique(array):
            new_ncpl[m] = 1
            for i in grid_info[m][0]:
                new_ncpl[m] *= i

        for mdl in np.unique(array):
            mnodes = np.where(array == mdl)[0]
            mg_info = grid_info[mdl]
            for nnode, onode in enumerate(mnodes):
                if mg_info[-1] is not None:
                    nnode = np.where(mg_info[-1] == onode)[0][0]
                self._node_map[onode] = (mdl, nnode)

        new_connections = {i: {"internal": {},
                               "external": {}
                               } for i in np.unique(array)}
        exchange_meta = {i: {} for i in np.unique(array)}
        usg_meta = {i: {} for i in np.unique(array)}
        for node, conn in self._connection.items():
            mdl, nnode = self._node_map[node]
            for ix, cnode in enumerate(conn):
                cmdl, cnnode = self._node_map[cnode]
                if cmdl == mdl:
                    if nnode in new_connections[mdl]["internal"]:
                        new_connections[mdl]["internal"][nnode].append(cnnode)
                        if self._connection_ivert is None:
                            usg_meta[mdl][nnode]["ihc"].append(
                                int(self._uconnection[node]["ihc"][ix + 1])
                            )
                            usg_meta[mdl][nnode]["cl12"].append(
                                self._uconnection[node]["cl12"][ix + 1]
                            )
                            usg_meta[mdl][nnode]["hwva"].append(
                                self._uconnection[node]["hwva"][ix + 1]
                            )

                    else:
                        new_connections[mdl]["internal"][nnode] = [cnnode]
                        if self._connection_ivert is None:
                            usg_meta[mdl][nnode] = {
                                "ihc": [self._uconnection[node]["ihc"][0],
                                        self._uconnection[node]["ihc"][ix + 1]],
                                "cl12": [self._uconnection[node]["cl12"][0],
                                         self._uconnection[node]["cl12"][ix + 1]],
                                "hwva": [self._uconnection[node]["hwva"][0],
                                         self._uconnection[node]["hwva"][ix + 1]]
                            }

                else:
                    if nnode in new_connections[mdl]["external"]:
                        new_connections[mdl]["external"][nnode].append(
                            (cmdl, cnnode)
                        )
                        if self._connection_ivert is not None:
                            exchange_meta[mdl][nnode][cnnode] = \
                                [node, cnode, self._connection_ivert[node][ix]]
                        else:
                            exchange_meta[mdl][nnode][cnnode] =  [
                                node, cnode,
                                self._uconnection[node]["ihc"][ix + 1],
                                self._uconnection[node]["cl12"][ix + 1],
                                self._uconnection[node]["hwva"][ix + 1]
                            ]
                    else:
                        new_connections[mdl]["external"][nnode] = [
                            (cmdl, cnnode)]
                        if self._connection_ivert is not None:
                            exchange_meta[mdl][nnode] = \
                                {cnnode: [node, cnode, self._connection_ivert[node][ix]]}
                        else:
                            exchange_meta[mdl][nnode] = \
                                {cnnode: [
                                    node, cnode,
                                    self._uconnection[node]["ihc"][ix + 1],
                                    self._uconnection[node]["cl12"][ix + 1],
                                    self._uconnection[node]["hwva"][ix + 1]
                                ]
                                }

        if self._modelgrid.grid_type == "vertex":
            self._map_verts_iverts(array)

        self._new_connections = new_connections
        self._new_ncpl = new_ncpl
        self._grid_info = grid_info
        self._exchange_metadata = exchange_meta
        self._usg_metadata = usg_meta

    def _map_iac_ja_connections(self):
        """
        Method to map connections in unstructured grids when no
        vertex information has been supplied

        """
        conn = {}
        uconn = {}
        # todo: put in PR removing the MFArray component in UnstructuredGrid
        iac = self._model.disu.iac.array
        ja = self._model.disu.ja.array
        cl12 = self._model.disu.cl12.array
        ihc = self._model.disu.ihc.array
        hwva = self._model.disu.hwva.array
        idx0 = 0
        for ia in iac:
            idx1 = idx0 + ia
            cn = ja[idx0 + 1: idx1]
            conn[ja[idx0]] = cn
            uconn[ja[idx0]] = {
                "cl12": cl12[idx0: idx1],
                "ihc": ihc[idx0: idx1],
                "hwva": hwva[idx0: idx1]
            }
            idx0 = idx1

        self._connection = conn
        self._uconnection = uconn

    def _map_connections(self):
        """
        Method to map connections between model cells
        """
        iverts = self._modelgrid.iverts
        iverts = self._irregular_shape_patch(iverts)  # todo: adapt flopy's plotutil
        iv_r = iverts[:, ::-1]

        conn = {}
        connivert = {}
        # todo: try updating neighbors with this change for speed improvements
        for node, iv in enumerate(iverts):
            cells = []
            vix = []
            for i in range(1, len(iv)):
                i0 = i - 1
                if iv[i] == iv[i0]:
                    continue
                for ii in range(1, len(iv)):
                    ii0 = ii - 1
                    idxn = np.where(
                        (iv_r[:, ii0] == iv[i0]) & (iv_r[:, ii] == iv[i]))
                    if len(idxn[0]) > 0:
                        for n in idxn[0]:
                            if n != node:
                                cells.append(n)
                                vix.append((iv[i0], iv[i]))

            conn[node] = np.array(cells)
            connivert[node] = vix
        self._connection = conn
        self._connection_ivert = connivert

    def _map_verts_iverts(self, array):
        """
        Method to create vertex and ivert look up tables

        Parameters
        ----------
        array : np.array
            integer array of model numbers

        """
        iverts = self._modelgrid.iverts
        verts = self._modelgrid.verts

        ivlut = {mkey: {} for mkey in np.unique(array)}
        for mkey in np.unique(array):
            new_iv = 0
            new_iverts = []
            new_verts = []
            tmp_vert_dict = {}
            for node, ivert in enumerate(iverts):
                tiverts = []
                mk, nnode = self._node_map[node]
                if mk == mkey:
                    for iv in ivert:
                        vert = tuple(verts[iv].tolist())
                        if vert in tmp_vert_dict:
                            tiverts.append(tmp_vert_dict[vert])
                        else:
                            tiverts.append(new_iv)
                            new_verts.append([new_iv] + list(vert))
                            tmp_vert_dict[vert] = new_iv
                            new_iv += 1

                    new_iverts.append(tiverts)

            ivlut[mkey]["iverts"] = new_iverts
            ivlut[mkey]["vertices"] = new_verts

        self._ivert_vert_remap = ivlut

    def _irregular_shape_patch(self, xverts, yverts=None):
        """
        DEPRECATED: remove and adapt plot_util's in final version

        Patch for vertex cross section plotting when
        we have an irregular shape type throughout the
        model grid or multiple shape types.

        Parameters
        ----------
        xverts : list
            xvertices
        yverts : list
            yvertices

        Returns
        -------
            xverts, yverts as np.ndarray

        """
        max_verts = 0

        for xv in xverts:
            if len(xv) > max_verts:
                max_verts = len(xv)

        if yverts is not None:
            for yv in yverts:
                if len(yv) > max_verts:
                    max_verts = len(yv)

        adj_xverts = []
        for xv in xverts:
            if len(xv) < max_verts:
                xv = list(xv)
                n = max_verts - len(xv)
                adj_xverts.append(xv + [xv[-1]] * n)
            else:
                adj_xverts.append(xv)

        if yverts is not None:
            adj_yverts = []
            for yv in yverts:
                if len(yv) < max_verts:
                    yv = list(yv)
                    n = max_verts - len(yv)
                    adj_yverts.append(yv + [yv[-1]] * n)
                else:
                    adj_yverts.append(yv)

            xverts = np.array(adj_xverts)
            yverts = np.array(adj_yverts)

            return xverts, yverts

        txverts = np.array(adj_xverts)
        xverts = np.zeros((txverts.shape[0], txverts.shape[1] + 1), dtype=int)
        xverts[:, 0:-1] = txverts
        xverts[:, -1] = xverts[:, 0]
        return xverts

    def _create_sln_tdis(self):
        """
        Method to create and add new TDIS and Solution Group objects
        from an existing Simulation

        Parameters
        ----------
        sim : MFSimulation object
            Simulation object that has a model that's being split
        new_sim : MFSimulation object
            New simulation object that will hold the split models

        Returns
        -------
            new_sim : MFSimulation object
        """
        for pak in self._sim.sim_package_list:
            pak_cls = PackageContainer.package_factory(pak.package_abbr,
                                                       "")
            signature = inspect.signature(pak_cls)
            d = {"simulation": self._new_sim, "loading_package": False}
            for key, value in signature.parameters.items():
                if key in ("simulation", "loading_package", "pname", "kwargs"):
                    continue
                elif key == "ats_perioddata":
                    # todo: figure out what needs to be done here. Child packages
                    #   seem like they are going to be a bit of an issue
                    continue
                else:
                    data = getattr(pak, key)
                    if hasattr(data, "array"):
                        d[key] = data.array
                    else:
                        d[key] = data

            new_pak = pak_cls(**d)

    def _remap_cell2d(self, item, cell2d, mapped_data):
        """
        Method to remap vertex grid cell2d

        Parameters
        ----------
        item : str
            parameter name string
        cell2d : MFList
            MFList object
        mapped_data : dict
            dictionary of remapped package data

        Returns
        -------
            dict
        """
        cell2d = cell2d.array

        for mkey in self._model_dict.keys():
            idx = []
            for node, (nmkey, nnode) in self._node_map.items():
                if nmkey == mkey:
                    idx.append(node)

            recarray = cell2d[idx]
            recarray["icell2d"] = range(len(recarray))
            iverts = self._irregular_shape_patch(self._ivert_vert_remap[mkey]["iverts"]).T
            for ix, ivert_col in enumerate(iverts[:-1]):
                recarray[f"icvert_{ix}"] = ivert_col

            mapped_data[mkey][item] = recarray

        return mapped_data

    def _remap_filerecords(self, item, value, mapped_data):
        """
        Method to create new file record names and map them to their
        associated models

        Parameters
        ----------
        item : str
            parameter name string
        value : MFList
            MFList object
        mapped_data : dict
            dictionary of remapped package data

        Returns
        -------
            dict
        """
        if item in (
                "budget_filerecord",
                "head_filerecord",
                "budgetcsv_filerecord",
                "stage_filerecord",
                "obs_filerecord"
        ):
            value = value.array
            if value is None:
                pass
            else:
                value = value[0][0]
                for mdl in mapped_data.keys():
                    new_val = value.split(".")
                    new_val = f"{'.'.join(new_val[0:-1])}_{mdl}.{new_val[-1]}"
                    mapped_data[mdl][item] = new_val
        return mapped_data

    def _remap_disu(self, mapped_data):
        """
        Method to remap DISU inputs to new grids

        Parameters
        ----------
        mapped_data : dict
            dictionary of model number and new package data

        Returns
        -------
        mapped_data : dict

        """
        for mkey, metadata in self._usg_metadata.items():
            iac, ja, ihc, cl12, hwva = [], [], [], [], []
            for node, params in metadata.items():
                conns = [node] + self._new_connections[mkey]["internal"][node]
                iac.append(len(conns))
                ja.extend(conns)
                ihc.extend(params["ihc"])
                cl12.extend(params["cl12"])
                hwva.extend(params["hwva"])

            assert np.sum(iac) == len(ja)

            mapped_data[mkey]["nja"] = len(ja)
            mapped_data[mkey]["iac"] = iac
            mapped_data[mkey]["ja"] = ja
            mapped_data[mkey]["ihc"] = ihc
            mapped_data[mkey]["cl12"] = cl12
            mapped_data[mkey]["hwva"] = hwva

        return mapped_data

    def _remap_array(self, item, mfarray, mapped_data):
        """
        Method to remap array nodes to each model

        Parameters
        ----------
        item : str
            variable name
        value : MFArray
            MFArray object
        mapped_data : dict
            dictionary of remapped package data

        Returns
        -------
            dict
        """
        if mfarray.array is None:
            return mapped_data

        if not hasattr(mfarray, "size"):
            mfarray = mfarray.array

        nlay = 1
        if isinstance(self._modelgrid.ncpl, (list, np.ndarray)):
            ncpl = self._modelgrid.nnodes
        else:
            ncpl = self._modelgrid.ncpl

        if mfarray.size == self._modelgrid.size:
            nlay = int(mfarray.size / ncpl)

        original_arr = mfarray.ravel()
        dtype = original_arr.dtype
        for layer in range(nlay):
            for node, (mkey, new_node) in self._node_map.items():
                node = node + (layer * ncpl)
                new_ncpl = self._new_ncpl[mkey]
                new_node = new_node + (layer * new_ncpl)
                value = original_arr[node]

                if item not in mapped_data[mkey]:
                    mapped_data[mkey][item] = np.zeros(new_ncpl * nlay, dtype=dtype)

                mapped_data[mkey][item][new_node] = value

        return mapped_data

    def _remap_mflist(self, item, mflist, mapped_data, transient=False):
        """
        Method to remap mflist data to each model

        Parameters
        ----------
        item : str
            variable name
        value : MFList
            MFList object
        mapped_data : dict
            dictionary of remapped package data
        transient : bool
            flag to indicate this is transient stress period data
            flag is needed to trap for remapping mover data.
        Returns
        -------
            dict
        """
        mvr_remap = {}
        if hasattr(mflist, "array"):
            if mflist.array is None:
                return mapped_data
            recarray = mflist.array
        else:
            recarray = mflist

        if "cellid" not in recarray.dtype.names:
            for model in self._model_dict.keys():
                mapped_data[model][item] = recarray.copy()
        else:
            cellids = recarray.cellid
            lay_num, nodes = self._cellid_to_layer_node(cellids)
            new_model, new_node = self._get_new_model_new_node(nodes)

            for mkey, model in self._model_dict.items():
                idx = np.where(new_model == mkey)[0]
                if self._pkg_mover and transient:
                    mvr_remap = {idx[i]: (model.name, i) for i in range(len(idx))}

                if len(idx) == 0:
                    new_recarray = None
                else:
                    new_cellids = self._new_node_to_cellid(model, new_node, lay_num, idx)
                    new_recarray = recarray[idx]
                    new_recarray["cellid"] = new_cellids

                mapped_data[mkey][item] = new_recarray

        if not transient:
            return mapped_data
        else:
            return mapped_data, mvr_remap

    def _remap_adv_transport(self, package, item, pkg_remap, mapped_data):
        """
        General method to remap advanced transport packages

        Parameters
        ----------
        package : flopy.mf6.Package
        item : str
        pkg_remap : dict
        mapped_data : dict

        Returns
        -------
            mapped_data : dict
        """
        flow_package_name = package.flow_package_name.array
        packagedata = package.packagedata.array
        perioddata = package.perioddata.data

        for mkey in self._model_dict.keys():
            flow_package_const = flow_package_name.split(".")
            new_packagedata = self._remap_adv_tag(
                mkey, packagedata, item, pkg_remap
            )
            if new_packagedata is None:
                continue

            spd = {}
            for per, recarray in perioddata.items():
                new_recarray = self._remap_adv_tag(
                    mkey, recarray, item, pkg_remap
                )
                spd[per] = new_recarray

            flow_package_const[-2] += f"_{mkey}"
            new_flow_package_name = ".".join(flow_package_const)
            mapped_data[mkey]["packagedata"] = new_packagedata
            mapped_data[mkey]["perioddata"] = spd
            mapped_data[mkey]["flow_package_name"] = new_flow_package_name
        return mapped_data

    def _remap_uzf(self, package, mapped_data):
        """
        Method to remap a UZF package, probably will work for UZT also
        need to check the input structure of UZT

        Parameters
        ----------
        package : ModflowGwfuzf
        mapped_data : dict
            dictionary of remapped package data

        Returns
        -------
            dict
        """
        obs_map = {"iuzno": {}}
        if isinstance(package, flopy.mf6.ModflowGwfuzf):
            packagedata = package.packagedata.array
            perioddata = package.perioddata.data
            cellids = packagedata.cellid
            layers, nodes = self._cellid_to_layer_node(cellids)
            new_model, new_node = self._get_new_model_new_node(nodes)

            mvr_remap = {}
            name = package.filename
            self._uzf_remaps[name] = {}
            for mkey, model in self._model_dict.items():
                idx = np.where(new_model == mkey)[0]
                if len(idx) == 0:
                    new_recarray = None
                else:
                    new_recarray = packagedata[idx]

                if new_recarray is not None:
                    uzf_remap = {i: ix for ix, i in enumerate(new_recarray.iuzno)}
                    if "boundname" in new_recarray.dtype.names:
                        for bname in new_recarray.boundname:
                            uzf_remap[bname] = bname

                    uzf_nodes = [i for i in uzf_remap.keys()]
                    uzf_remap[-1] = -1
                    for oid, nid in uzf_remap.items():
                        mvr_remap[oid] = (model.name, nid)
                        self._uzf_remaps[name][oid] = (mkey, nid)
                        obs_map["iuzno"][oid] = (mkey, nid)

                    new_cellids = self._new_node_to_cellid(model, new_node, layers, idx)
                    new_recarray["cellid"] = new_cellids
                    new_recarray["iuzno"] = [uzf_remap[i] for i in new_recarray["iuzno"]]
                    new_recarray["ivertcon"] = [uzf_remap[i] for i in new_recarray["ivertcon"]]

                    obs_map = self._set_boundname_remaps(
                        new_recarray, obs_map, list(obs_map.keys()), mkey
                    )

                    spd = {}
                    for per, recarray in perioddata.items():
                        idx = np.where(np.isin(recarray.iuzno, uzf_nodes))
                        new_period = recarray[idx]
                        new_period["iuzno"] = [uzf_remap[i] for i in new_period['iuzno']]
                        spd[per] = new_period

                    mapped_data[mkey]['packagedata'] = new_recarray
                    mapped_data[mkey]['nuzfcells'] = len(new_recarray)
                    mapped_data[mkey]['ntrailwaves'] = package.ntrailwaves.array
                    mapped_data[mkey]['nwavesets'] = package.nwavesets.array
                    mapped_data[mkey]["perioddata"] = spd

            if self._pkg_mover:
                for per in range(self._model.nper):
                    if per in self._mover_remaps:
                        self._mover_remaps[per][package.name[0]] = mvr_remap
                    else:
                        self._mover_remaps[per] = {package.name[0]: mvr_remap}
        else:
            name = package.flow_package_name.array
            uzf_remap = self._uzf_remaps[name]
            mapped_data = self._remap_adv_transport(package, "iuzno", uzf_remap, mapped_data)

        for obspak in package.obs._packages:
            mapped_data = self._remap_obs(
                obspak,
                mapped_data,
                obs_map["iuzno"],
                pkg_type=package.package_type
            )

        return mapped_data

    def _remap_mvr(self, package, mapped_data):
        """
        Method to remap internal and external movers from an existing
        MVR package

        Parameters
        ----------
        package : ModflowGwfmvr
        mapped_data : dict
            dictionary of remapped package data

        Returns
        -------
            dict
        """
        # self._mvr_remaps = {}
        if isinstance(package, flopy.mf6.ModflowGwtmvt):
            return mapped_data

        perioddata = package.perioddata.data
        for mkey, model in self._model_dict.items():
            spd = {}
            maxmvr = 0
            for per, recarray in perioddata.items():
                mover_remaps = self._mover_remaps[per]
                new_records = []
                externals = []
                for rec in recarray:
                    mname1, nid1 = mover_remaps[rec.pname1][rec.id1]
                    if mname1 != model.name:
                        continue
                    mname2, nid2 = mover_remaps[rec.pname2][rec.id2]
                    if mname1 != mname2:
                        new_rec = (mname1, rec.pname1, nid1, mname2, rec.pname2, nid2, rec.mvrtype, rec.value)
                        externals.append(new_rec)
                    else:
                        new_rec = (rec.pname1, nid1, rec.pname2, nid2, rec.mvrtype, rec.value)
                        new_records.append(new_rec)

                if new_records:
                    if len(new_records) > maxmvr:
                        maxmvr = len(new_records)

                    spd[per] = new_records

                if externals:
                    if per in self._sim_mover_data:
                        for rec in externals:
                            self._sim_mover_data[per].append(rec)
                    else:
                        self._sim_mover_data[per] = externals

            if spd:
                mapped_data[mkey]["perioddata"] = spd
                mapped_data[mkey]["maxmvr"] = maxmvr
                mapped_data[mkey]["maxpackages"] = len(package.packages.array)
                mapped_data[mkey]["packages"] = package.packages.array

        return mapped_data

    def _remap_lak(self, package, mapped_data):
        """
        Method to remap an existing LAK package

        Parameters
        ----------
        package : ModflowGwflak
        mapped_data : dict
            dictionary of remapped package data

        Returns
        -------
            dict
        """
        packagedata = package.packagedata.array
        perioddata = package.perioddata.data

        obs_map = {"lakeno": {}, "outletno": {}}
        if isinstance(package, flopy.mf6.ModflowGwflak):
            connectiondata = package.connectiondata.array
            tables = package.tables.array
            outlets = package.outlets.array

            lak_remaps = {}
            name = package.filename
            self._lak_remaps[name] = {}
            cellids = connectiondata.cellid
            layers, nodes = self._cellid_to_layer_node(cellids)

            new_model, new_node = self._get_new_model_new_node(nodes)

            for mkey, model in self._model_dict.items():
                idx = np.where(new_model == mkey)[0]
                if len(idx) == 0:
                    new_recarray = None
                else:
                    new_recarray = connectiondata[idx]

                if new_recarray is not None:
                    new_cellids = self._new_node_to_cellid(model, new_node, layers, idx)
                    new_recarray["cellid"] = new_cellids

                    for nlak, lak in enumerate(sorted(np.unique(new_recarray.lakeno))):
                        lak_remaps[lak] = (mkey, nlak)
                        self._lak_remaps[name][lak] = (mkey, nlak)
                        obs_map["lakeno"][lak] = (mkey, nlak)

                    new_lak = [lak_remaps[i][-1] for i in new_recarray.lakeno]
                    new_recarray["lakeno"] = new_lak

                    new_packagedata = self._remap_adv_tag(mkey, packagedata, "lakeno", lak_remaps)

                    new_tables = None
                    if tables is not None:
                        new_tables = self._remap_adv_tag(mkey, tables, "lakeno", lak_remaps)

                    new_outlets = None
                    if outlets is not None:
                        mapnos = []
                        for lak, meta in lak_remaps.items():
                            if meta[0] == mkey:
                                mapnos.append(lak)

                        idxs = np.where(np.isin(outlets.lakein, mapnos))[0]
                        if len(idxs) == 0:
                            new_outlets = None
                        else:
                            new_outlets = outlets[idxs]
                            lakein = [lak_remaps[i][-1] for i in new_outlets.lakein]
                            lakeout = [lak_remaps[i][-1] if i in lak_remaps else -1 for i in new_outlets.lakeout]
                            for nout, out in enumerate(sorted(np.unique(new_outlets.outletno))):
                                obs_map["outletno"][out] = (mkey, nout)

                            outletno = list(range(len(new_outlets)))
                            new_outlets["outletno"] = outletno
                            new_outlets["lakein"] = lakein
                            new_outlets["lakeout"] = lakeout

                    # set boundnames to the observation remapper
                    obs_map = self._set_boundname_remaps(
                        new_packagedata, obs_map, list(obs_map.keys()), mkey
                    )

                    spd = {}
                    for k, recarray in perioddata.items():
                        new_ra = self._remap_adv_tag(mkey, recarray, "number", lak_remaps)
                        spd[k] = new_ra

                    if new_recarray is not None:
                        mapped_data[mkey]["connectiondata"] = new_recarray
                        mapped_data[mkey]["packagedata"] = new_packagedata
                        mapped_data[mkey]["tables"] = new_tables
                        mapped_data[mkey]["outlets"] = new_outlets
                        mapped_data[mkey]["perioddata"] = spd
                        mapped_data[mkey]["nlakes"] = len(new_packagedata.lakeno)
                        if new_outlets is not None:
                            mapped_data[mkey]["noutlets"] = len(new_outlets)
                        if new_tables is not None:
                            mapped_data[mkey]["ntables"] = len(new_tables)

            if self._pkg_mover:
                self._set_mover_remaps(package, lak_remaps)
        else:
            name = package.flow_package_name.array
            lak_remap = self._lak_remaps[name]
            mapped_data = self._remap_adv_transport(
                package, "lakno", lak_remap, mapped_data
            )

        for obspak in package.obs._packages:
            mapped_data = self._remap_obs(
                obspak, mapped_data, obs_map, pkg_type=package.package_type
            )

        return mapped_data

    def _remap_sfr(self, package, mapped_data):
        """
        Method to remap an existing SFR package

        Parameters
        ----------
        package : ModflowGwfsfr
        mapped_data : dict
            dictionary of remapped package data

        Returns
        -------
            dict
        """
        obs_map = {"rno": {}}
        if isinstance(package, flopy.mf6.ModflowGwfsfr):
            packagedata = package.packagedata.array
            crosssections = package.crosssections.array
            connectiondata = package.connectiondata.array
            diversions = package.diversions.array
            perioddata = package.perioddata.data
            name = package.filename
            self._sfr_remaps[name] = {}
            sfr_remaps = {}
            div_mvr_conn = {}
            sfr_mvr_conn = []
            cellids = packagedata.cellid
            layers, nodes = self._cellid_to_layer_node(cellids)

            new_model, new_node = self._get_new_model_new_node(nodes)

            for mkey, model in self._model_dict.items():
                idx = np.where(new_model == mkey)[0]
                if len(idx) == 0:
                    new_recarray = None
                else:
                    new_recarray = packagedata[idx]

                if new_recarray is not None:
                    new_cellids = self._new_node_to_cellid(model, new_node, layers, idx)
                    new_recarray["cellid"] = new_cellids

                    new_rno = []
                    old_rno = []
                    for ix, rno in enumerate(new_recarray.rno):
                        new_rno.append(ix)
                        old_rno.append(rno)
                        sfr_remaps[rno] = (mkey, ix)
                        sfr_remaps[-1 * rno] = (mkey, -1 * ix)
                        self._sfr_remaps[name][rno] = (mkey, ix)
                        obs_map['rno'][rno] = (mkey, ix)

                    new_recarray["rno"] = new_rno
                    obs_map = self._set_boundname_remaps(
                        new_recarray, obs_map, ['rno'], mkey
                    )

                    # now let's remap connection data and tag external exchanges
                    idx = np.where(np.isin(connectiondata.rno, old_rno))[0]
                    new_connectiondata = connectiondata[idx]
                    ncons = []
                    for ix, rec in enumerate(new_connectiondata):
                        new_rec = []
                        nan_count = 0
                        for item in new_connectiondata.dtype.names:
                            if rec[item] in sfr_remaps:
                                mn, nrno = sfr_remaps[rec[item]]
                                if mn != mkey:
                                    nan_count += 1
                                else:
                                    new_rec.append(sfr_remaps[rec[item]][-1])
                            elif np.isnan(rec[item]):
                                nan_count += 1
                            else:
                                # this is an instance where we need to map
                                # external connections!
                                nan_count += 1
                                if rec[item] < 0:
                                    # downstream connection
                                    sfr_mvr_conn.append((rec["rno"], int(abs(rec[item]))))
                                else:
                                    sfr_mvr_conn.append((int(rec[item]), rec["rno"]))
                        # sort the new_rec so nan is last
                        ncons.append(len(new_rec) - 1)
                        if nan_count > 0:
                            new_rec += [np.nan,] * nan_count
                        new_connectiondata[ix] = tuple(new_rec)

                    # now we need to go back and change ncon....
                    new_recarray["ncon"] = ncons

                    new_crosssections = None
                    if crosssections is not None:
                        new_crosssections = self._remap_adv_tag(
                            mkey, crosssections, "rno", sfr_remaps
                        )

                    new_diversions = None
                    div_mover_ix = []
                    if diversions is not None:
                        # first check if diversion outlet is outside the model
                        for ix, rec in enumerate(diversions):
                            rno = rec.rno
                            iconr = rec.iconr
                            if rno not in sfr_remaps and iconr not in sfr_remaps:
                                continue
                            elif rno in sfr_remaps and iconr not in sfr_remaps:
                                div_mover_ix.append(ix)
                            else:
                                m0 = sfr_remaps[rno][0]
                                m1 = sfr_remaps[iconr][0]
                                if m0 != m1:
                                    div_mover_ix.append(ix)

                        idx = np.where(np.isin(diversions.rno, old_rno))[0]
                        idx = np.where(~np.isin(idx, div_mover_ix))[0]

                        new_diversions = diversions[idx]
                        new_rno = [sfr_remaps[i][-1] for i in new_diversions.rno]
                        new_iconr = [sfr_remaps[i][-1] for i in new_diversions.iconr]
                        new_idv = list(range(len(new_diversions)))
                        new_diversions["rno"] = new_rno
                        new_diversions["iconr"] = new_iconr
                        new_diversions["idv"] = new_idv

                        externals = diversions[div_mover_ix]
                        for rec in externals:
                            div_mvr_conn[rec["idv"]] = [rec["rno"], rec["iconr"], rec["cprior"]]

                    # now we can do the stress period data
                    spd = {}
                    for kper, recarray in perioddata.items():
                        idx = np.where(np.isin(recarray.rno, old_rno))[0]
                        new_spd = recarray[idx]
                        if diversions is not None:
                            external_divs = np.where(
                                np.isin(new_spd.idv, list(div_mvr_conn.keys()))
                            )[0]
                            if len(external_divs) > 0:
                                for ix in external_divs:
                                    rec = recarray[ix]
                                    idv = recarray["idv"]
                                    div_mvr_conn[idv].append(rec["divflow"])

                            idx = np.where(
                                ~np.isin(new_spd.idv, list(div_mvr_conn.keys()))
                            )[0]

                            new_spd = new_spd[idx]

                        # now to renamp the rnos...
                        new_rno = [sfr_remaps[i][-1] for i in new_spd.rno]
                        new_spd["rno"] = new_rno
                        spd[kper] = new_spd

                    mapped_data[mkey]["packagedata"] = new_recarray
                    mapped_data[mkey]["connectiondata"] = new_connectiondata
                    mapped_data[mkey]["crosssections"] = new_crosssections
                    mapped_data[mkey]["diversions"] = new_diversions
                    mapped_data[mkey]["perioddata"] = spd
                    mapped_data[mkey]["nreaches"] = len(new_recarray)

            # connect model network through movers between models
            mvr_recs = []
            for rec in sfr_mvr_conn:
                m0, n0 = sfr_remaps[rec[0]]
                m1, n1 = sfr_remaps[rec[1]]
                mvr_recs.append((self._model_dict[m0].name, package.name[0], n0,
                                 self._model_dict[m1].name, package.name[0], n1,
                                 "FACTOR", 1))

            for idv, rec in div_mvr_conn.items():
                m0, n0 = sfr_remaps[rec[0]]
                m1, n1 = sfr_remaps[rec[1]]
                mvr_recs.append((self._model_dict[m0].name, package.name[0], n0,
                                 self._model_dict[m1].name, package.name[0], n1,
                                 rec[2], rec[3]))

            if mvr_recs:
                for mkey in self._model_dict.keys():
                    mapped_data[mkey]["mover"] = True
                for per in range(self._model.nper):
                    if per in self._sim_mover_data:
                        for rec in mvr_recs:
                            self._sim_mover_data[per].append(rec)
                    else:
                        self._sim_mover_data[per] = mvr_recs

            # create a remap table for movers between models
            if self._pkg_mover:
                self._set_mover_remaps(package, sfr_remaps)
        else:
            flow_package_name = package.flow_package_name.array
            sfr_remap = self._sfr_remaps[flow_package_name]
            mapped_data = self._remap_adv_transport(
                package, "rno", sfr_remap, mapped_data
            )

        for obspak in package.obs._packages:
            mapped_data = self._remap_obs(
                obspak, mapped_data, obs_map['rno'], pkg_type=package.package_type
            )

        return mapped_data

    def _remap_maw(self, package, mapped_data):
        """
        Method to remap a Multiaquifer well package

        Parameters
        ----------
        package : ModflowGwfmaw
        mapped_data : dict
            dictionary of remapped package data

        Returns
        -------
            dict
        """
        obs_map = {"wellno": {}}
        if isinstance(package, flopy.mf6.ModflowGwfmaw):
            connectiondata = package.connectiondata.array
            packagedata = package.packagedata.array
            perioddata = package.perioddata.data
            name = package.filename
            self._maw_remaps[name] = {}

            cellids = connectiondata.cellid
            layers, nodes = self._cellid_to_layer_node(cellids)
            new_model, new_node = self._get_new_model_new_node(nodes)
            maw_remaps = {}

            for mkey, model in self._model_dict.items():
                idx = np.where(new_model == mkey)[0]
                new_connectiondata = connectiondata[idx]
                if len(new_connectiondata) == 0:
                    continue
                else:
                    new_cellids = self._new_node_to_cellid(
                        model, new_node, layers, idx
                    )

                    maw_wellnos = []
                    for nmaw, maw in enumerate(sorted(np.unique(new_connectiondata.wellno))):
                        maw_wellnos.append(maw)
                        maw_remaps[maw] = (mkey, nmaw)
                        self._maw_remaps[maw] = (mkey, nmaw)
                        obs_map["wellno"][maw] = (mkey, nmaw)

                    new_wellno = [maw_remaps[wl][-1] for wl in new_connectiondata.wellno]
                    new_connectiondata["cellid"] = new_cellids
                    new_connectiondata["wellno"] = new_wellno

                    obs_map = self._set_boundname_remaps(
                        new_connectiondata, obs_map, ["wellno"], mkey
                    )

                    new_packagedata = self._remap_adv_tag(
                        mkey, packagedata, "wellno", maw_remaps
                    )

                    spd = {}
                    for per, recarray in perioddata.items():
                        idx = np.where(np.isin(recarray.wellno, maw_wellnos))[0]
                        if len(idx) > 0:
                            new_recarray = recarray[idx]
                            new_wellno = [maw_remaps[wl][-1] for wl in new_recarray.wellno]
                            new_recarray["wellno"] = new_wellno
                            spd[per] = new_recarray

                    mapped_data[mkey]["nmawwells"] = len(new_packagedata)
                    mapped_data[mkey]["packagedata"] = new_packagedata
                    mapped_data[mkey]["connectiondata"] = new_connectiondata
                    mapped_data[mkey]["perioddata"] = spd

            if self._pkg_mover:
                self._set_mover_remaps(package, maw_remaps)
        else:
            flow_package_name = package.flow_package_name.array
            maw_remap = self._maw_remaps[flow_package_name]
            mapped_data = self._remap_adv_transport(
                package, "mawno", maw_remap, mapped_data
            )

        for obspak in package.obs._packages:
            mapped_data = self._remap_obs(
                obspak,
                mapped_data,
                obs_map['wellno'],
                pkg_type=package.package_type
            )

        return mapped_data

    def _remap_csub(self, package, mapped_data):
        """
        Method to remap the CSUB package

        Parameters
        ----------
        package : ModflowGwfcsub
        mapped_data : dict
            dictionary of remapped package data

        Returns
        -------
            dict
        """
        mapped_data = self._remap_array("cg_ske_cr", package.cg_ske_cr, mapped_data)
        mapped_data = self._remap_array("cg_theta", package.cg_theta, mapped_data)
        mapped_data = self._remap_array("sgm", package.sgm, mapped_data)
        mapped_data = self._remap_array("sgs", package.sgs, mapped_data)

        packagedata = package.packagedata.array
        stress_period_data = package.stress_period_data.array

        cellids = packagedata.cellid
        layers, nodes = self._cellid_to_layer_node(cellids)
        new_model, new_node = self._get_new_model_new_node(nodes)

        ninterbeds = None
        for mkey, model in self._model_dict.items():
            idx = np.where(new_model == mkey)[0]
            if len(idx) == 0:
                new_packagedata = None
            else:
                new_packagedata = packagedata[idx]

            if new_packagedata is not None:
                new_cellids = self._new_node_to_cellid(model, new_node, layers, idx)
                new_packagedata["cellid"] = new_cellids
                new_packagedata["ninterbeds"] = list(range(len(new_packagedata)))
                ninterbeds = len(new_packagedata)

            spd = {}
            maxsigo = 0
            for per, recarray in stress_period_data.items():
                layers, nodes = self._cellid_to_layer_node(recarray.cellid)
                new_model, new_node = self._get_new_model_new_node(nodes)

                idx = np.where(new_model == mkey)[0]
                if len(idx) == 0:
                    continue

                new_recarray = recarray[idx]
                new_cellids = self._new_node_to_cellid(model, new_node, layers, idx)
                new_recarray["cellid"] = new_cellids

                if len(new_recarray) > maxsigo:
                    maxsigo = len(new_recarray)

                spd[per] = new_recarray

            mapped_data["packagedata"] = new_packagedata
            mapped_data["stress_period_data"] = spd
            mapped_data["ninterbeds"] = ninterbeds
            mapped_data["maxsigo"] = maxsigo

        return mapped_data

    def _set_boundname_remaps(self, recarray, obs_map, variables, mkey):
        """

        Parameters
        ----------
        recarray:
        obs_map:
        variables:
        mkey:

        Returns
        -------
            dict : obs_map
        """
        if "boundname" in recarray.dtype.names:
            for bname in recarray.boundname:
                for variable in variables:
                    if bname in obs_map[variable]:
                        if not isinstance(obs_map[variable][bname], list):
                            obs_map[variable][bname] = [obs_map[variable][bname]]
                        obs_map[variable][bname].append((mkey, bname))
                    else:
                        obs_map[variable][bname] = (mkey, bname)

        return obs_map
                
    def _set_mover_remaps(self, package, pkg_remap):
        """
        Method to set remaps that can be used later to remap the mover
        package

        Parameters
        ----------
        package : flopy.mf6.Package
            any flopy package that can be a receiver or provider in the
            mover package
        pkg_remap : dict
            dictionary of remapped package data, such as
            {old well number : (new model name, new well number)}

        """
        mvr_remap = {}
        for oid, (mkey, nid) in pkg_remap.items():
            if oid < 0:
                continue
            name = self._model_dict[mkey].name
            mvr_remap[oid] = (name, nid)

        for per in range(self._model.nper):
            if per in self._mover_remaps:
                self._mover_remaps[per][package.name[0]] = mvr_remap

            else:
                self._mover_remaps[per] = {package.name[0]: mvr_remap}
        
    def _remap_hfb(self, package, mapped_data):
        """
        Method to remap a horizontal flow barrier package

        Parameters
        ----------
        package : ModflowGwfhfb
        mapped_data : dict
            dictionary of remapped package data

        Returns
        -------
            dict
        """
        spd = {}
        for per, recarray in package.stress_period_data.data.items():
            per_dict = {}
            cellids1 = recarray.cellid1
            cellids2 = recarray.cellid2
            layers1, nodes1 = self._cellid_to_layer_node(cellids1)
            layers2, nodes2 = self._cellid_to_layer_node(cellids2)
            new_model1, new_node1 = self._get_new_model_new_node(nodes1)
            new_model2, new_node2 = self._get_new_model_new_node(nodes2)
            if not (new_model1 == new_model2).all():
                raise AssertionError("Models cannot be split along faults")

            for mkey, model in self._model_dict.items():
                idx = np.where(new_model1 == mkey)[0]
                if len(idx) == 0:
                    new_recarray = None
                else:
                    new_recarray = recarray[idx]

                if new_recarray is not None:
                    new_cellids1 = self._new_node_to_cellid(
                        model, new_node1, layers1, idx
                    )
                    new_cellids2 = self._new_node_to_cellid(
                        model, new_node2, layers2, idx
                    )
                    new_recarray["cellid1"] = new_cellids1
                    new_recarray["cellid2"] = new_cellids2
                    per_dict[mkey] = new_recarray

            for mkey, rec in per_dict.items():
                if "stress_period_data" not in mapped_data[mkey]:
                    mapped_data[mkey]["stress_period_data"] = {per: rec}
                else:
                    mapped_data[mkey]['stress_period_data'][per] = rec

        return mapped_data

    def _remap_fmi(self, package, mapped_data):
        """
        Method to remap a flow model interface package

        Parameters
        ----------
        package : ModflowGwtfmi
        mapped_data : dict
            dictionary of remapped package data

        Returns
        -------
            dict
        """
        packagedata = package.packagedata.array
        fnames = packagedata.fname

        for mkey in self._model_dict.keys():
            new_fnames = []
            for fname in fnames:
                new_val = fname.split(".")
                new_val = f"{'.'.join(new_val[0:-1])}_{mkey}.{new_val[-1]}"
                new_fnames.append(new_val)

            new_packagedata = packagedata.copy()
            new_packagedata["fname"] = new_fnames
            mapped_data[mkey]["packagedata"] = new_packagedata

        return mapped_data

    def _remap_obs(self, package, mapped_data, remapper, pkg_type=None):
        """
        Method to remap an observation package

        Parameters
        ----------
        package : ModflowUtlobs
        mapped_data : dict
            dictionary of remapped package data

        Returns
        -------
            dict
        """
        if isinstance(package, flopy.mf6.ModflowUtlobs):
            obs_packages = [package,]
        else:
            if hasattr(package, "obs"):
                obs_packages = package.obs._packages
            else:
                obs_packages = []

        obs_data = {mkey: {} for mkey in self._model_dict.keys()}
        mm_keys = {}
        mm_idx = []
        for obs_package in obs_packages:
            continuous_data = obs_package.continuous.data
            for ofile, recarray in continuous_data.items():
                if pkg_type is None:
                    layers1, node1 = self._cellid_to_layer_node(recarray.id)
                    new_node1 = np.array([remapper[i][-1] for i in node1], dtype=int)
                    new_model1 = np.array([remapper[i][0] for i in node1], dtype=int)

                    new_cellid1 = np.full((len(recarray,)), None, dtype=object)
                    for mkey, model in self._model_dict.items():
                        idx = np.where(new_model1 == mkey)
                        tmp_cellid = self._new_node_to_cellid(model, new_node1, layers1, idx)
                        new_cellid1[idx] = tmp_cellid
                else:
                    obstype = OBS_ID1_LUT[pkg_type]
                    if obstype != "cellid":
                        obsid = []
                        for i in recarray.id:
                            try:
                                obsid.append(int(i) - 1)
                            except ValueError:
                                obsid.append(i)

                        obsid = np.array(obsid, dtype=object)
                        if isinstance(obstype, dict):
                            new_cellid1 = np.full(len(recarray), None, dtype=object)
                            new_model1 = np.full(len(recarray), None, dtype=object)
                            obstypes = [obstype for obstype in recarray.obstype]
                            idtype = np.array([OBS_ID1_LUT[pkg_type][otype] for otype in obstypes], dtype=object)
                            for idt in set(idtype):
                                remaps = remapper[idt]
                                idx = np.where(idtype == idt)
                                new_cellid1[idx] = [remaps[i][-1] + 1 if isinstance(i, int) else i for i in obsid[idx]]
                                new_model1[idx] = [remaps[i][0] for i in obsid[idx]]

                        else:
                            new_cellid1 = np.array(
                                [remapper[i][-1] + 1 if isinstance(i, int) else i for i in obsid],
                                dtype=object
                            )
                            new_model1 = np.array([remapper[i][0] for i in obsid], dtype=object)

                    else:
                        new_node1 = np.full((len(recarray),), None, dtype=object)
                        new_model1 = np.full((len(recarray),), None, dtype=object)

                        bidx = [ix for ix, i in enumerate(recarray.id) if isinstance(i, str)]
                        idx = [ix for ix, i in enumerate(recarray.id) if not isinstance(i, str)]
                        layers1, node1 = self._cellid_to_layer_node(recarray.id[idx])
                        new_node1[idx] = [remapper[i][-1] for i in node1]
                        new_model1[idx] = [remapper[i][0] for i in node1]
                        new_node1[bidx] = [i for i in recarray.id[bidx]]
                        new_model1[bidx] = [remapper[i][0] for i in recarray.id[bidx]]

                        new_cellid1 = np.full((len(recarray, )), None, dtype=object)
                        for mkey, model in self._model_dict.items():
                            idx = np.where(new_model1 == mkey)
                            idx = [ix for ix, i in enumerate(recarray.id[idx]) if not isinstance(i, str)]
                            tmp_cellid = self._new_node_to_cellid(model, new_node1, layers1, idx)
                            new_cellid1[idx] = tmp_cellid

                        new_cellid1[bidx] = new_node1[bidx]

                    # check if any boundnames cross model boundaries
                    if isinstance(obstype, dict):
                        remap = remapper[list(remapper.keys())[0]]
                    else:
                        remap = remapper
                    mm_idx = [idx for idx, v in enumerate(new_model1) if
                              isinstance(v, tuple)]
                    for idx in mm_idx:
                        key = new_model1[idx][-1]
                        for mdl, bname in remap[key]:
                            if key in mm_keys:
                                mm_keys[key].append(mdl)
                            else:
                                mm_keys[key] = [mdl]

                    tmp_models = [new_model1[idx][0] for idx in mm_idx]
                    new_model1[mm_idx] = tmp_models

                cellid2 = recarray.id2
                conv_idx = np.where((cellid2 != None))[0]
                if len(conv_idx) > 0: # do stuff
                    # need to trap layers...
                    if pkg_type is None:
                        if self._modelgrid.grid_type in ('structured', "vertex"):
                            layers2 = [cid[0] if cid is not None else None for cid in cellid2]
                            if self._modelgrid.grid_type == "structured":
                                cellid2 = [(0, cid[1], cid[2]) if cid is not None else None for cid in cellid2]
                            else:
                                cellid2 = [(0, cid[1]) if cid is not None else None for cid in cellid2]

                        node2 = self._modelgrid.get_node(list(cellid2[conv_idx]))
                        new_node2 = np.full((len(recarray),), None, dtype=object)
                        new_model2 = np.full((len(recarray),), None, dtype=object)

                        new_node2[conv_idx] = [remapper[i][-1] for i in node2]
                        new_model2[conv_idx] = [remapper[i][0] for i in node2]
                        for ix in range(len(recarray)):
                            if ix in conv_idx:
                                continue
                            else:
                                new_node2.append(None)
                                new_model2.append(new_model1[ix])

                        if not np.allclose(new_model1, new_model2):
                            raise AssertionError(
                                "One or more observation records cross model boundaries"
                            )

                        new_cellid2 = np.full((len(new_node2),), None, dtype=object)
                        for mkey, model in self._model_dict.items():
                            idx = np.where(new_model2 == mkey)
                            tmp_node = new_node2[idx]
                            cidx = np.where((tmp_node != None))
                            tmp_cellid = model.modelgrid.get_lrc(tmp_node[cidx].to_list())
                            if self._modelgrid.grid_type in ("structured", "vertex"):
                                tmp_layers = layers2[cidx]
                                tmp_cellid = [(tmp_layers[ix],) + cid[1:] for ix, cid in enumerate(tmp_cellid)]

                            tmp_node[cidx] = tmp_cellid
                            new_cellid2[idx] = tmp_node
                    else:
                        obstype = OBS_ID2_LUT[pkg_type]
                        if obstype is None:
                            new_cellid2 = cellid2
                        else:
                            obsid = []
                            for i in recarray.id2:
                                try:
                                    obsid.append(int(i) - 1)
                                except ValueError:
                                    obsid.append(i)
                            if isinstance(obstype, dict):
                                new_cellid2 = np.full(len(recarray), None, dtype=object)
                                obstypes = [obstype for obstype in recarray.obstype]
                                idtype = np.array([OBS_ID2_LUT[pkg_type][otype] for otype in obstypes], dtype=object)
                                for idt in set(idtype):
                                    if idt is None:
                                        continue
                                    remaps = remapper[idt]
                                    idx = np.where(idtype == idt)
                                    new_cellid2[idx] = [remaps[i][-1] + 1 if isinstance(i, int) else i for i in obsid[idx]]
                            else:
                                new_cellid2 = np.array([remapper[i][-1] + 1 if isinstance(i, int) else i for i in obsid], dtype=object)

                else:
                    new_cellid2 = cellid2

                for mkey in self._model_dict.keys():
                    # adjust model numbers if boundname crosses models
                    if mm_keys:
                        for idx in mm_idx:
                            bname = new_cellid1[idx]
                            model_nums = mm_keys[bname]
                            if mkey in model_nums:
                                new_model1[idx] = mkey

                    # now we remap the continuous data!!!!
                    idx = np.where(new_model1 == mkey)[0]
                    if len(idx) == 0:
                        continue

                    new_recarray = recarray[idx]
                    new_recarray.id = new_cellid1[idx]
                    new_recarray.id2 = new_cellid2[idx]

                    # remap file names
                    if isinstance(ofile, (list, tuple)):
                        fname = ofile[0]
                        tmp = fname.split(".")
                        tmp[-2] += f"_{mkey}"
                        ofile[0] = ".".join(tmp)
                    else:
                        tmp = ofile.split(".")
                        tmp[-2] += f"_{mkey}"
                        ofile = ".".join(tmp)

                    if pkg_type is None:
                        if "continuous" not in mapped_data[mkey]:
                            mapped_data[mkey]["continuous"] = {ofile: new_recarray}
                        else:
                            mapped_data[mkey]["continuous"][ofile] = new_recarray
                    else:
                        if "observations" not in mapped_data:
                            mapped_data["observations"] = {mkey: {} for mkey in self._model_dict.keys()}

                        if "continuous" not in mapped_data[mkey]:
                            mapped_data["observations"][mkey]["continuous"] = {ofile: new_recarray}
                        else:
                            mapped_data["observations"][mkey]["continuous"][ofile] = new_recarray

        return mapped_data

    def _cellid_to_layer_node(self, cellids):
        """
        Method to convert cellids to node numbers

        Parameters
        ----------
        cellids : np.array
            array of cellids

        Returns
        -------
        tuple (list of layers, list of nodes)
        """
        if self._modelgrid.grid_type == "structured":
            layers = np.array([i[0] for i in cellids])
            cellids = [(0, i[1], i[2]) for i in cellids]
            nodes = self._modelgrid.get_node(cellids)
        elif self._modelgrid.grid_type == "vertex":
            layers = np.array([i[0] for i in cellids])
            nodes = [i[1] for i in cellids]
        else:
            nodes = [i[0] for i in cellids]
            layers = None

        return layers, nodes

    def _get_new_model_new_node(self, nodes):
        """
        Method to get new model number and node number from the node map

        Parameters
        ----------
        nodes : list, np.ndarray
            iterable of model node numbers

        Returns
        -------
        tuple (list, list) list of new model numbers and new node numbers

        """
        new_model = np.zeros((len(nodes),), dtype=int)
        new_node = np.zeros((len(nodes),), dtype=int)
        for ix, node in enumerate(nodes):
            nm, nn = self._node_map[node]
            new_model[ix] = nm
            new_node[ix] = nn

        return new_model, new_node

    def _new_node_to_cellid(self, model, new_node, layers, idx):
        """
        Method to convert nodes to cellids

        Parameters
        ----------
        model : flopy.mf6.MFModel object
        new_node : list
            list of node numbers
        layers : list
            list of layer numbers
        idx: : list
            index of node numbers to convert to cellids

        Returns
        -------
            list : new cellid numbers
        """

        new_node = new_node[idx].astype(int)
        if self._modelgrid.grid_type == "structured":
            new_node += (layers[idx] * model.modelgrid.ncpl)
            new_cellids = model.modelgrid.get_lrc(
                new_node.astype(int)
            )
        elif self._modelgrid.grid_type == "vertex":
            new_cellids = [
                tuple(cid) for cid in zip(layers[idx], new_node)
            ]

        else:
            new_cellids = [(i,) for i in new_node]

        return new_cellids

    def _remap_adv_tag(self, mkey, recarray, item, mapper):
        """
        Method to remap advanced package ids such as SFR's rno varaible

        Parameters
        ----------
        recarray : np.recarray
        item : str
            variable name to remap
        mapper : dict
            dictionary of {old id: (new model number, new id)}

        Returns
        -------
            np.recarray
        """
        mapnos = []
        for lak, meta in mapper.items():
            if meta[0] == mkey:
                mapnos.append(lak)

        idxs = np.where(np.isin(recarray[item], mapnos))[0]
        if len(idxs) == 0:
            new_recarray = None
        else:
            new_recarray = recarray[idxs]
            newnos = [mapper[i][-1] for i in new_recarray[item]]
            new_recarray[item] = newnos
        return new_recarray

    def _remap_transient_list(self, item, mftransientlist, mapped_data):
        """
        Method to remap transient list data to each model

        Parameters
        ----------
        item : str
            parameter name
        mftransientlist : MFTransientList
            MFTransientList object
        mapped_data : dict
            dictionary of remapped package data

        Returns
        -------
            dict
        """
        d0 = {mkey: {} for mkey in self._model_dict.keys()}
        if mftransientlist.data is None:
            for mkey in self._model_dict.keys():
                mapped_data[mkey][item] = None
            return mapped_data

        for per, recarray in mftransientlist.data.items():
            d, mvr_remaps = self._remap_mflist(item, recarray, mapped_data, transient=True)
            for mkey in self._model_dict.keys():
                if mapped_data[mkey][item] is None:
                    continue
                d0[mkey][per] = mapped_data[mkey][item]

            if mvr_remaps:
                if per in self._mover_remaps:
                    self._mover_remaps[per][self._pkg_mover_name] = mvr_remaps
                else:
                    self._mover_remaps[per] = {
                        self._pkg_mover_name : mvr_remaps
                    }

        for mkey in self._model_dict.keys():
            mapped_data[mkey][item] = d0[mkey]

        return mapped_data

    def _remap_package(self, package, ismvr=False):
        """
        Method to remap package data to new packages in each model

        Parameters
        ----------
        package : flopy.mf6.Package
            Package object
        ismvr : bool
            boolean flag to indicate that this is a mover package
            to remap

        Returns
        -------
            dict
        """
        # todo: child packages??? This is an issue that still needs solving.

        mapped_data = {mkey: {} for mkey in self._model_dict.keys()}

        # check to see if the package has active movers
        self._pkg_mover = False
        if hasattr(package, 'mover'):
            if package.mover.array:
                self._pkg_mover = True
                self._pkg_mover_name = package.name[0]

        if isinstance(
                package,
                (flopy.mf6.modflow.ModflowGwfdis,
                 flopy.mf6.modflow.ModflowGwfdisu,
                 flopy.mf6.modflow.ModflowGwtdis,
                 flopy.mf6.modflow.ModflowGwtdisu)
        ):
            for item, value in package.__dict__.items():
                if item in ('delr', "delc"):
                    for mkey, d in self._grid_info.items():
                        if item == "delr":
                            i0, i1 = d[2]
                        else:
                            i0, i1 = d[1]

                        mapped_data[mkey][item] = value.array[i0:i1 + 1]

                elif item in ("nrow", "ncol"):
                    for mkey, d in self._grid_info.items():
                        if item == "nrow":
                            i0, i1 = d[1]
                        else:
                            i0, i1 = d[2]

                        mapped_data[mkey][item] = (i1 - i0) + 1

                elif item == "nlay":
                    for mkey in self._model_dict.keys():
                        mapped_data[mkey][item] = value.array

                elif item == "nodes":
                    for mkey in self._model_dict.keys():
                        mapped_data[mkey][item] = self._grid_info[mkey][0][0]

                elif item == "iac":
                    mapped_data = self._remap_disu(mapped_data)
                    break

                elif item == "xorigin":
                    for mkey in self._model_dict.keys():
                        for k, v in self._offsets[mkey].items():
                            mapped_data[mkey][k] = v

                elif isinstance(value, flopy.mf6.data.mfdataarray.MFArray):
                    mapped_data = self._remap_array(item, value, mapped_data)

        elif isinstance(package, flopy.mf6.ModflowGwfhfb):
            mapped_data = self._remap_hfb(package, mapped_data)

        elif isinstance(package, flopy.mf6.ModflowGwfcsub):
            mapped_data = self._remap_csub(package, mapped_data)

        elif isinstance(package, (flopy.mf6.ModflowGwfuzf, flopy.mf6.ModflowGwtuzt)):
            mapped_data = self._remap_uzf(package, mapped_data)

        elif isinstance(package, (flopy.mf6.ModflowGwfmaw, flopy.mf6.ModflowGwtmwt)):
            mapped_data = self._remap_maw(package, mapped_data)

        elif ismvr:
            self._remap_mvr(package, mapped_data)

        elif isinstance(package, (flopy.mf6.ModflowGwfmvr, flopy.mf6.ModflowGwtmvt)):
            self._mover = True
            return {}

        elif isinstance(package, (flopy.mf6.ModflowGwflak, flopy.mf6.ModflowGwtlkt)):
            mapped_data = self._remap_lak(package, mapped_data)

        elif isinstance(package, (flopy.mf6.ModflowGwfsfr, flopy.mf6.ModflowGwtsft)):
            mapped_data = self._remap_sfr(package, mapped_data)

        elif isinstance(package, flopy.mf6.ModflowUtlobs):
            if package.parent_file is not None:
                return {}
            mapped_data = self._remap_obs(package, mapped_data, self._node_map)

        elif isinstance(package, flopy.mf6.ModflowGwtfmi):
            mapped_data = self._remap_fmi(package, mapped_data)

        else:
            for item, value in package.__dict__.items():
                if item.startswith("_"):
                    continue

                elif item == "nvert":
                    continue

                elif item in ("ncpl", "nodes"):
                    for mkey in self._model_dict.keys():
                        mapped_data[mkey][item] = self._grid_info[mkey][0][0]

                elif item.endswith("_filerecord"):
                    mapped_data = self._remap_filerecords(item, value, mapped_data)

                elif item in ('vertices', "cell2d"):
                    if value.array is not None:
                        if item == "cell2d":
                            mapped_data = self._remap_cell2d(item, value, mapped_data)
                        else:
                            for mkey in self._model_dict.keys():
                                mapped_data[mkey][item] = self._ivert_vert_remap[mkey][item]
                                mapped_data[mkey]["nvert"] = len(self._ivert_vert_remap[mkey][item])

                elif item == "xorigin":
                    for mkey in self._model_dict.keys():
                        for k, v in self._offsets[mkey].items():
                            mapped_data[mkey][k] = v

                elif isinstance(value, flopy.mf6.data.mfdataarray.MFArray):
                    mapped_data = self._remap_array(item, value, mapped_data)

                elif isinstance(value, flopy.mf6.data.mfdatalist.MFTransientList):
                    mapped_data = self._remap_transient_list(item, value, mapped_data)

                elif isinstance(value, flopy.mf6.data.mfdatalist.MFList):
                    mapped_data = self._remap_mflist(item, value, mapped_data)

                elif isinstance(value, flopy.mf6.data.mfdatascalar.MFScalar):
                    for mkey in self._model_dict.keys():
                        mapped_data[mkey][item] = value.data
                else:
                    pass

        observations = mapped_data.pop("observations", None)

        if "options" in package.blocks:
            for item, value in package.blocks["options"].datasets.items():
                if item.endswith("_filerecord"):
                    mapped_data = self._remap_filerecords(item, value, mapped_data)
                    continue

                elif item in ("flow_package_name", "xorigin", "yorigin"):
                    continue

                for mkey in mapped_data.keys():
                    if isinstance(value, flopy.mf6.data.mfdatascalar.MFScalar):
                        mapped_data[mkey][item] = value.data
                    elif isinstance(value, flopy.mf6.data.mfdatalist.MFList):
                        mapped_data[mkey][item] = value.array

        pak_cls = PackageContainer.package_factory(package.package_type,
                                                   self._model_type)
        paks = {}
        for mdl, data in mapped_data.items():
            paks[mdl] = pak_cls(self._model_dict[mdl],
                                pname=package.name[0],
                                **data)

        if observations is not None:
            for mdl, data in observations.items():
                if data:
                    parent = paks[mdl]
                    filename = f"{parent.quoted_filename}.obs"
                    obs = flopy.mf6.ModflowUtlobs(
                        parent, pname="obs", filename=filename, **data
                    )

        return paks

    def _create_exchanges(self):
        """
        Method to create exchange packages for fluxes between models

        Returns
        -------
            dict
        """
        d = {}
        built = []
        nmodels = list(self._model_dict.keys())
        if self._model.name_file.newtonoptions is not None:
            newton = self._model.name_file.newtonoptions.array
            if isinstance(newton, list):
                newton = True
        else:
            newton = None

        if self._model_type.lower() == "gwf":
            exchgtype = "GWF6-GWF6"
            extension = "gwfgwf"
            exchgcls = flopy.mf6.ModflowGwfgwf
        elif self._model_type.lower() == "gwt":
            exchgtype = "GWT6-GWT6"
            extension = "gwtgwt"
            exchgcls = flopy.mf6.ModflowGwtgwt
        else:
            raise NotImplementedError()

        if self._modelgrid.grid_type == "unstructured":
            # use existing connection information
            aux = False
            for m0, model in self._model_dict.items():
                exg_nodes = self._new_connections[m0]["external"]
                for m1 in nmodels:
                    if m1 in built:
                        continue
                    if m1 == m0:
                        continue
                    exchange_data = []
                    for node0, exg_list in exg_nodes.items():
                        for exg in exg_list:
                            if exg[0] != m1:
                                continue
                            node1 = exg[-1]
                            exg_meta0 = self._exchange_metadata[m0][node0][node1]
                            exg_meta1 = self._exchange_metadata[m1][node1][node0]
                            rec = ((node0,), (node1,), 1, exg_meta0[3], exg_meta1[3], exg_meta0[-1])
                            exchange_data.append(rec)

                    if exchange_data:
                        mname0 = self._model_dict[m0].name
                        mname1 = self._model_dict[m1].name
                        exchg = exchgcls(
                            self._new_sim,
                            exgtype=exchgtype,
                            # todo open an issue about this! This should be explicitly set when running create_package.py!
                            exgmnamea=mname0,
                            exgmnameb=mname1,
                            nexg=len(exchange_data),
                            exchangedata=exchange_data,
                            filename=f"sim_{m0}_{m1}.{extension}",
                            newton=newton
                        )
                        d[f"{mname0}_{mname1}"] = exchg

                built.append(m0)

            for _, model in self._model_dict.items():
                # turn off save_specific_discharge if it's on
                model.npf.save_specific_discharge = None

        else:
            xc = self._modelgrid.xcellcenters.ravel()
            yc = self._modelgrid.ycellcenters.ravel()
            verts = self._modelgrid.verts
            for m0, model in self._model_dict.items():
                exg_nodes = self._new_connections[m0]["external"]
                for m1 in nmodels:
                    if m1 in built:
                        continue
                    if m1 == m0:
                        continue
                    modelgrid0 = model.modelgrid
                    modelgrid1 = self._model_dict[m1].modelgrid
                    ncpl0 = modelgrid0.ncpl
                    ncpl1 = modelgrid1.ncpl
                    exchange_data = []
                    for node0, exg_list in exg_nodes.items():
                        for exg in exg_list:
                            if exg[0] != m1:
                                continue

                            node1 = exg[1]
                            for layer in range(self._modelgrid.nlay):
                                if self._modelgrid.grid_type == "structured":
                                    tmpnode0 = node0 + (ncpl0 * layer)
                                    tmpnode1 = node1 + (ncpl1 * layer)
                                    cellidm0 = modelgrid0.get_lrc([tmpnode0])[0]
                                    cellidm1 = modelgrid1.get_lrc([tmpnode1])[0]
                                elif self._modelgrid.grid_type == "vertex":
                                    cellidm0 = (layer, node0)
                                    cellidm1 = (layer, node1)
                                else:
                                    cellidm0 = node0
                                    cellidm1 = node1

                                if modelgrid0.idomain is not None:
                                    if modelgrid0.idomain[cellidm0] <= 0:
                                        continue
                                if modelgrid1.idomain is not None:
                                    if modelgrid1.idomain[cellidm1] <= 0:
                                        continue
                                # calculate CL1, CL2 from exchange metadata
                                meta = self._exchange_metadata[m0][node0][node1]
                                ivrt = meta[2]
                                x1 = xc[meta[0]]
                                y1 = yc[meta[0]]
                                x2 = xc[meta[1]]
                                y2 = yc[meta[1]]
                                x3, y3 = verts[ivrt[0]]
                                x4, y4 = verts[ivrt[1]]

                                numa = (x4 - x3) * (y1 - y3) - (y4 - y3) * (x1 - x3)
                                denom = (y4 - y3) * (x2 - x1) - (x4 - x3) * (y2 - y1)
                                ua = numa / denom
                                x = x1 + ua * (x2 - x1)
                                y = y1 + ua * (y2 - y1)

                                cl0 = np.sqrt((x - x1) ** 2 + (y - y1) ** 2)
                                cl1 = np.sqrt((x - x2) ** 2 + (y - y2) ** 2)
                                hwva = np.sqrt((x3 - x4) ** 2 + (y3 - y4) ** 2)

                                # calculate angledegx and cdist
                                angledegx = np.arctan2([y2 - y1], [x2 - x1])[0] * (180 / np.pi)
                                if angledegx < 0:
                                    angledegx = 360 + angledegx

                                cdist = np.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)

                                rec = [cellidm0, cellidm1, 1, cl0, cl1, hwva, angledegx, cdist]
                                exchange_data.append(rec)

                    mvr_data = {}
                    packages = []
                    maxmvr = 0
                    for per, mvrs in self._sim_mover_data.items():
                        mname0 = self._model_dict[m0].name
                        mname1 = self._model_dict[m1].name
                        records = []
                        for rec in mvrs:
                            if rec[0] == mname0 or rec[3] == mname0:
                                if rec[0] == mname1 or rec[3] == mname1:
                                    records.append(rec)
                                    if rec[1] not in packages:
                                        packages.append((rec[0], rec[1]))
                                    if rec[4] not in packages:
                                        packages.append((rec[3], rec[4]))
                        if records:
                            if len(records) > maxmvr:
                                maxmvr = len(records)
                            mvr_data[per] = records

                    if exchange_data or mvr_data:
                        mname0 = self._model_dict[m0].name
                        mname1 = self._model_dict[m1].name
                        exchg = exchgcls(
                            self._new_sim,
                            exgtype=exchgtype, # todo open an issue about this! This should be explicitly set when running create_package.py!
                            exgmnamea=mname0,
                            exgmnameb=mname1,
                            auxiliary=["ANGLDEGX", "CDIST"],
                            nexg=len(exchange_data),
                            exchangedata=exchange_data,
                            filename=f"sim_{m0}_{m1}.{extension}",
                            newton=newton
                        )
                        d[f"{mname0}_{mname1}"] = exchg

                        if mvr_data:
                            mvr = flopy.mf6.modflow.ModflowGwfmvr(
                                exchg,
                                modelnames=True,
                                maxmvr=maxmvr,
                                maxpackages=len(packages),
                                packages=packages,
                                perioddata=mvr_data
                            )

                        d[f"{mname0}_{mname1}_mvr"] = exchg

                built.append(m0)

        return d

    def split_model(self, array):
        """
        User method to split a model based on an array

        Parameters
        ----------
        array : np.ndarray
            integer array of new model numbers. Array must either be of
            dimension (NROW, NCOL), (NCPL), or (NNODES for unstructured grid
            models).

        Returns
        -------
            MFSimulation object
        """
        self._remap_nodes(array)

        if self._new_sim is None:
            self._new_sim = flopy.mf6.MFSimulation()
            self._create_sln_tdis()


        nam_options = {}
        for item, value in self._model.name_file.blocks["options"].datasets.items():
            if item == "list":
                continue
            nam_options[item] = value.array
        self._model_dict = {}
        for mkey in self._new_ncpl.keys():

            mdl_cls = PackageContainer.model_factory(self._model_type)
            self._model_dict[mkey] = mdl_cls(
                self._new_sim, modelname=f"{self._modelname}_{mkey}", **nam_options
            )

        for package in self._model.packagelist:
            paks = self._remap_package(package)

        if self._mover:
            mover = self._model.mvr
            self._remap_package(mover, ismvr=True)

        epaks = self._create_exchanges()

        return self._new_sim


# todo: development notes:
#   Package obs...
#   Then set up checks for model splitting
#       (ex. doesnt parallel a fault, doesnt cut through a lake, active cells in modelgrid...)
#   Finally deal with subpackages...