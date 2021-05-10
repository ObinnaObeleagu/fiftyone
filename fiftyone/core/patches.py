"""
Patches views.

| Copyright 2017-2021, Voxel51, Inc.
| `voxel51.com <https://voxel51.com/>`_
|
"""
from copy import deepcopy

import eta.core.utils as etau

import fiftyone.core.aggregations as foa
import fiftyone.core.dataset as fod
import fiftyone.core.fields as fof
import fiftyone.core.labels as fol
import fiftyone.core.media as fom
import fiftyone.core.sample as fos
import fiftyone.core.utils as fou
import fiftyone.core.view as fov

fouc = fou.lazy_import("fiftyone.utils.eval.coco")


_SINGLE_TYPES_MAP = {
    fol.Detections: fol.Detection,
    fol.Polylines: fol.Polyline,
}
_PATCHES_TYPES = (fol.Detections, fol.Polylines)
_NO_MATCH_ID = ""


class _PatchView(fos.SampleView):
    def save(self):
        super().save()
        self._view._sync_source_sample(self)


class PatchView(_PatchView):
    """A patch in a :class:`PatchesView`.

    :class:`PatchView` instances should not be created manually; they are
    generated by iterating over :class:`PatchesView` instances.

    Args:
        doc: a :class:`fiftyone.core.odm.DatasetSampleDocument`
        view: the :class:`PatchesView` that the patch belongs to
        selected_fields (None): a set of field names that this view is
            restricted to
        excluded_fields (None): a set of field names that are excluded from
            this view
        filtered_fields (None): a set of field names of list fields that are
            filtered in this view
    """

    pass


class EvaluationPatchView(_PatchView):
    """A patch in an :class:`EvaluationPatchesView`.

    :class:`EvaluationPatchView` instances should not be created manually; they
    are generated by iterating over :class:`EvaluationPatchesView` instances.

    Args:
        doc: a :class:`fiftyone.core.odm.DatasetSampleDocument`
        view: the :class:`EvaluationPatchesView` that the patch belongs to
        selected_fields (None): a set of field names that this view is
            restricted to
        excluded_fields (None): a set of field names that are excluded from
            this view
        filtered_fields (None): a set of field names of list fields that are
            filtered in this view
    """

    pass


class _PatchesView(fov.DatasetView):
    def __init__(
        self, source_collection, patches_stage, patches_dataset, _stages=None
    ):
        if _stages is None:
            _stages = []

        self._source_collection = source_collection
        self._patches_stage = patches_stage
        self._patches_dataset = patches_dataset
        self.__stages = _stages

    def __copy__(self):
        return self.__class__(
            self._source_collection,
            deepcopy(self._patches_stage),
            self._patches_dataset,
            _stages=deepcopy(self.__stages),
        )

    @property
    def _label_fields(self):
        raise NotImplementedError("subclass must implement _label_fields")

    @property
    def _dataset(self):
        return self._patches_dataset

    @property
    def _root_dataset(self):
        return self._source_collection._root_dataset

    @property
    def _stages(self):
        return self.__stages

    @property
    def _all_stages(self):
        return (
            self._source_collection.view()._all_stages
            + [self._patches_stage]
            + self.__stages
        )

    @property
    def _element_str(self):
        return "patch"

    @property
    def _elements_str(self):
        return "patches"

    @property
    def name(self):
        return self.dataset_name + "-patches"

    @classmethod
    def _get_default_sample_fields(
        cls, include_private=False, include_id=False
    ):
        fields = super()._get_default_sample_fields(
            include_private=include_private, include_id=include_id
        )

        return fields + ("sample_id",)

    def set_values(self, field_name, *args, **kwargs):
        field = field_name.split(".", 1)[0]
        must_sync = field in self._label_fields

        # The `set_values()` operation could change the contents of this view,
        # so we first record the sample IDs that need to be synced
        if must_sync and self._stages:
            ids = self.values("_id")
        else:
            ids = None

        super().set_values(field_name, *args, **kwargs)

        if must_sync:
            self._sync_source_field(field, ids=ids)

    def save(self, fields=None):
        if etau.is_str(fields):
            fields = [fields]

        super().save(fields=fields)

        if fields is None:
            fields = self._label_fields
        else:
            fields = [l for l in fields if l in self._label_fields]

        #
        # IMPORTANT: we sync the contents of `_patches_dataset`, not `self`
        # here because the `save()` call above updated the dataset, which means
        # this view may no longer have the same contents (e.g., if `skip()` is
        # involved)
        #

        self._sync_source_root(fields)

    def reload(self):
        self._root_dataset.reload()

        #
        # Regenerate the patches dataset
        #
        # This assumes that calling `load_view()` when the current patches
        # dataset has been deleted will cause a new one to be generated
        #

        self._patches_dataset.delete()
        _view = self._patches_stage.load_view(self._source_collection)
        self._patches_dataset = _view._patches_dataset

    def _sync_source_sample(self, sample):
        for field in self._label_fields:
            self._sync_source_sample_field(sample, field)

    def _sync_source_sample_field(self, sample, field):
        label_type = self._patches_dataset._get_label_field_type(field)
        is_list_field = issubclass(label_type, fol._LABEL_LIST_FIELDS)

        doc = sample._doc.field_to_mongo(field)
        if is_list_field:
            doc = doc[label_type._LABEL_LIST_FIELD]

        self._source_collection._set_labels_by_id(
            field, [sample.sample_id], [doc]
        )

    def _sync_source_field(self, field, ids=None):
        _, label_path = self._patches_dataset._get_label_field_path(field)

        if ids is not None:
            view = self._patches_dataset.mongo(
                [{"$match": {"_id": {"$in": ids}}}]
            )
        else:
            view = self._patches_dataset

        sample_ids, docs = view.aggregate(
            [foa.Values("sample_id"), foa.Values(label_path, _raw=True)]
        )

        self._source_collection._set_labels_by_id(field, sample_ids, docs)

    def _sync_source_root(self, fields):
        for field in fields:
            self._sync_source_root_field(field)

    def _sync_source_root_field(self, field):
        _, id_path = self._get_label_field_path(field, "id")
        label_path = id_path.rsplit(".", 1)[0]

        #
        # Sync label updates
        #

        sample_ids, docs, label_ids = self._patches_dataset.aggregate(
            [
                foa.Values("sample_id"),
                foa.Values(label_path, _raw=True),
                foa.Values(id_path, unwind=True),
            ]
        )

        self._source_collection._set_labels_by_id(field, sample_ids, docs)

        #
        # Sync label deletions
        #

        _, src_id_path = self._source_collection._get_label_field_path(
            field, "id"
        )
        src_ids = self._source_collection.values(src_id_path, unwind=True)
        delete_ids = set(src_ids) - set(label_ids)

        if delete_ids:
            self._source_collection._dataset.delete_labels(
                ids=delete_ids, fields=field
            )

    def _get_ids_map(self, field):
        label_type = self._patches_dataset._get_label_field_type(field)
        is_list_field = issubclass(label_type, fol._LABEL_LIST_FIELDS)

        _, id_path = self._get_label_field_path(field, "id")

        sample_ids, label_ids = self.aggregate(
            [foa.Values("id"), foa.Values(id_path)]
        )

        ids_map = {}
        if is_list_field:
            for sample_id, _label_ids in zip(sample_ids, label_ids):
                if not _label_ids:
                    continue

                for label_id in _label_ids:
                    ids_map[label_id] = sample_id

        else:
            for sample_id, label_id in zip(sample_ids, label_ids):
                if not label_id:
                    continue

                ids_map[label_id] = sample_id

        return ids_map


class PatchesView(_PatchesView):
    """A :class:`fiftyone.core.view.DatasetView` of patches from a
    :class:`fiftyone.core.dataset.Dataset`.

    Patches views contain an ordered collection of patch samples, each of which
    contains a subset of a sample of the parent dataset corresponding to a
    single object or logical grouping of of objects.

    Patches retrieved from patches views are returned as :class:`PatchView`
    objects.

    Args:
        source_collection: the
            :class:`fiftyone.core.collections.SampleCollection` from which this
            view was created
        patches_stage: the :class:`fiftyone.core.stages.ToPatches` stage that
            defines how the patches were extracted
        patches_dataset: the :class:`fiftyone.core.dataset.Dataset` that serves
            the patches in this view
    """

    _SAMPLE_CLS = PatchView

    def __init__(
        self, source_collection, patches_stage, patches_dataset, _stages=None
    ):
        super().__init__(
            source_collection, patches_stage, patches_dataset, _stages=_stages
        )

        self._patches_field = patches_stage.field

    @property
    def _label_fields(self):
        return [self._patches_field]

    @property
    def patches_field(self):
        """The field from which the patches in this view were extracted."""
        return self._patches_field


class EvaluationPatchesView(_PatchesView):
    """A :class:`fiftyone.core.view.DatasetView` containing evaluation patches
    from a :class:`fiftyone.core.dataset.Dataset`.

    Evalation patches views contain an ordered collection of evaluation
    examples, each of which contains the ground truth and/or predicted labels
    for a true positive, false positive, or false negative example from an
    evaluation run on the underlying dataset.

    Patches retrieved from patches views are returned as
    :class:`EvaluationPatchView` objects.

    Args:
        source_collection: the
            :class:`fiftyone.core.collections.SampleCollection` from which this
            view was created
        patches_stage: the :class:`fiftyone.core.stages.ToEvaluationPatches`
            stage that defines how the patches were extracted
        patches_dataset: the :class:`fiftyone.core.dataset.Dataset` that serves
            the patches in this view
    """

    _SAMPLE_CLS = EvaluationPatchView

    def __init__(
        self, source_collection, patches_stage, patches_dataset, _stages=None
    ):
        super().__init__(
            source_collection, patches_stage, patches_dataset, _stages=_stages
        )

        eval_key = patches_stage.eval_key
        eval_info = source_collection.get_evaluation_info(eval_key)
        self._gt_field = eval_info.config.gt_field
        self._pred_field = eval_info.config.pred_field

    @property
    def _label_fields(self):
        return [self._gt_field, self._pred_field]

    @property
    def gt_field(self):
        """The ground truth field for the evaluation patches in this view."""
        return self._gt_field

    @property
    def pred_field(self):
        """The predictions field for the evaluation patches in this view."""
        return self._pred_field


def make_patches_dataset(
    sample_collection, field, keep_label_lists=False, name=None
):
    """Creates a dataset that contains one sample per object patch in the
    specified field of the collection.

    Fields other than ``field`` and the default sample fields will not be
    included in the returned dataset. A ``sample_id`` field will be added that
    records the sample ID from which each patch was taken.

    Args:
        sample_collection: a
            :class:`fiftyone.core.collections.SampleCollection`
        field: the patches field, which must be of type
            :class:`fiftyone.core.labels.Detections` or
            :class:`fiftyone.core.labels.Polylines`
        keep_label_lists (False): whether to store the patches in label list
            fields of the same type as the input collection rather than using
            their single label variants
        name (None): a name for the returned dataset

    Returns:
        a :class:`fiftyone.core.dataset.Dataset`
    """
    if keep_label_lists:
        field_type = sample_collection._get_label_field_type(field)
    else:
        field_type = _get_single_label_field_type(sample_collection, field)

    dataset = fod.Dataset(name, _patches=True)
    dataset.media_type = fom.IMAGE
    dataset.add_sample_field("sample_id", fof.StringField)
    dataset.add_sample_field(
        field, fof.EmbeddedDocumentField, embedded_doc_type=field_type
    )

    patches_view = _make_patches_view(
        sample_collection, field, keep_label_lists=keep_label_lists
    )
    _write_samples(dataset, patches_view)

    return dataset


def _get_single_label_field_type(sample_collection, field):
    label_type = sample_collection._get_label_field_type(field)

    if label_type not in _SINGLE_TYPES_MAP:
        raise ValueError("Unsupported label field type %s" % label_type)

    return _SINGLE_TYPES_MAP[label_type]


def make_evaluation_dataset(sample_collection, eval_key, name=None):
    """Creates a dataset based on the results of the evaluation with the given
    key that contains one sample for each true positive, false positive, and
    false negative example in the input collection, respectively.

    True positive examples will result in samples with both their ground truth
    and predicted fields populated, while false positive/negative examples will
    only have one of their corresponding predicted/ground truth fields
    populated, respectively.

    If multiple predictions are matched to a ground truth object (e.g., if the
    evaluation protocol includes a crowd attribute), then all matched
    predictions will be stored in the single sample along with the ground truth
    object.

    The returned dataset will also have top-level ``type`` and ``iou`` fields
    populated based on the evaluation results for that example, as well as a
    ``sample_id`` field recording the sample ID of the example, and a ``crowd``
    field if the evaluation protocol defines a crowd attribute.

    .. note::

        The returned dataset will contain patches for the contents of the input
        collection, which may differ from the view on which the ``eval_key``
        evaluation was performed. This may exclude some labels that were
        evaluated and/or include labels that were not evaluated.

        If you would like to see patches for the exact view on which an
        evaluation was performed, first call
        :meth:`load_evaluation_view() <fiftyone.core.collections.SampleCollection.load_evaluation_view`
        to load the view and then convert to patches.

    Args:
        sample_collection: a
            :class:`fiftyone.core.collections.SampleCollection`
        eval_key: an evaluation key that corresponds to the evaluation of
            ground truth/predicted fields that are of type
            :class:`fiftyone.core.labels.Detections` or
            :class:`fiftyone.core.labels.Polylines`
        name (None): a name for the returned dataset

    Returns:
        a :class:`fiftyone.core.dataset.Dataset`
    """
    # Parse evaluation info
    eval_info = sample_collection.get_evaluation_info(eval_key)
    pred_field = eval_info.config.pred_field
    gt_field = eval_info.config.gt_field
    if isinstance(eval_info.config, fouc.COCOEvaluationConfig):
        crowd_attr = eval_info.config.iscrowd
    else:
        crowd_attr = None

    pred_type = sample_collection._get_label_field_type(pred_field)
    gt_type = sample_collection._get_label_field_type(gt_field)

    # Setup dataset with correct schema
    dataset = fod.Dataset(name, _patches=True)
    dataset.media_type = fom.IMAGE
    dataset.add_sample_field(
        pred_field, fof.EmbeddedDocumentField, embedded_doc_type=pred_type
    )
    dataset.add_sample_field(
        gt_field, fof.EmbeddedDocumentField, embedded_doc_type=gt_type
    )
    dataset.add_sample_field("sample_id", fof.StringField)
    dataset.add_sample_field("type", fof.StringField)
    dataset.add_sample_field("iou", fof.FloatField)
    if crowd_attr is not None:
        dataset.add_sample_field("crowd", fof.BooleanField)

    # Add ground truth patches
    gt_view = _make_eval_view(
        sample_collection, eval_key, gt_field, crowd_attr=crowd_attr
    )
    _write_samples(dataset, gt_view)

    # Merge matched predictions
    _merge_matched_labels(dataset, sample_collection, eval_key, pred_field)

    # Add unmatched predictions
    unmatched_pred_view = _make_eval_view(
        sample_collection, eval_key, pred_field, skip_matched=True
    )
    _add_samples(dataset, unmatched_pred_view)

    return dataset


def _make_patches_view(sample_collection, field, keep_label_lists=False):
    if sample_collection._is_frame_field(field):
        raise ValueError(
            "Frame label patches cannot be directly extracted; you must first "
            "convert your video dataset into a frame dataset"
        )

    label_type = sample_collection._get_label_field_type(field)
    if issubclass(label_type, _PATCHES_TYPES):
        list_field = field + "." + label_type._LABEL_LIST_FIELD
    else:
        raise ValueError(
            "Invalid label field type %s. Extracting patches is only "
            "supported for the following types: %s"
            % (label_type, _PATCHES_TYPES)
        )

    pipeline = [
        {
            "$project": {
                "_id": 1,
                "_media_type": 1,
                "filepath": 1,
                "metadata": 1,
                "tags": 1,
                field + "._cls": 1,
                list_field: 1,
            }
        },
        {"$unwind": "$" + list_field},
        {
            "$set": {
                "sample_id": {"$toString": "$_id"},
                "_rand": {"$rand": {}},
            }
        },
        {"$set": {"_id": "$" + list_field + "._id"}},
    ]

    if keep_label_lists:
        pipeline.append({"$set": {list_field: ["$" + list_field]}})
    else:
        pipeline.append({"$set": {field: "$" + list_field}})

    return sample_collection.mongo(pipeline)


def _make_eval_view(
    sample_collection, eval_key, field, skip_matched=False, crowd_attr=None
):
    eval_type = field + "." + eval_key
    eval_id = field + "." + eval_key + "_id"
    eval_iou = field + "." + eval_key + "_iou"

    view = _make_patches_view(sample_collection, field)

    if skip_matched:
        view = view.mongo(
            [
                {
                    "$match": {
                        "$expr": {
                            "$or": [
                                {"$eq": ["$" + eval_id, _NO_MATCH_ID]},
                                {"$not": {"$gt": ["$" + eval_id, None]}},
                            ]
                        }
                    }
                }
            ]
        )

    view = view.mongo(
        [{"$set": {"type": "$" + eval_type, "iou": "$" + eval_iou}}]
    )

    if crowd_attr is not None:
        crowd_path1 = "$" + field + "." + crowd_attr
        crowd_path2 = "$" + field + ".attributes." + crowd_attr + ".value"
        view = view.mongo(
            [
                {
                    "$set": {
                        "crowd": {
                            "$cond": {
                                "if": {"$gt": [crowd_path1, None]},
                                "then": {"$toBool": crowd_path1},
                                "else": {
                                    "$cond": {
                                        "if": {"$gt": [crowd_path2, None]},
                                        "then": {"$toBool": crowd_path2},
                                        "else": None,
                                    }
                                },
                            }
                        }
                    }
                }
            ]
        )

    return _upgrade_labels(view, field)


def _upgrade_labels(view, field):
    tmp_field = "_" + field
    label_type = view._get_label_field_type(field)
    return view.mongo(
        [
            {"$set": {tmp_field: "$" + field}},
            {"$unset": field},
            {
                "$set": {
                    field: {
                        "_cls": label_type.__name__,
                        label_type._LABEL_LIST_FIELD: ["$" + tmp_field],
                    }
                }
            },
            {"$unset": tmp_field},
        ]
    )


def _merge_matched_labels(dataset, src_collection, eval_key, field):
    field_type = src_collection._get_label_field_type(field)

    list_field = field + "." + field_type._LABEL_LIST_FIELD
    eval_id = eval_key + "_id"
    foreign_key = "key"

    lookup_pipeline = src_collection._pipeline(detach_frames=True)
    lookup_pipeline.extend(
        [
            {"$project": {list_field: 1}},
            {"$unwind": "$" + list_field},
            {"$replaceRoot": {"newRoot": "$" + list_field}},
            {
                "$match": {
                    "$expr": {
                        "$and": [
                            {"$ne": ["$" + eval_id, _NO_MATCH_ID]},
                            {
                                "$eq": [
                                    {"$toObjectId": "$" + eval_id},
                                    "$$" + foreign_key,
                                ]
                            },
                        ]
                    }
                }
            },
        ]
    )

    pipeline = [
        {"$set": {field + "._cls": field_type.__name__}},
        {
            "$lookup": {
                "from": src_collection._dataset._sample_collection_name,
                "let": {foreign_key: "$_id"},
                "pipeline": lookup_pipeline,
                "as": list_field,
            }
        },
        {
            "$set": {
                field: {
                    "$cond": {
                        "if": {"$gt": [{"$size": "$" + list_field}, 0]},
                        "then": "$" + field,
                        "else": None,
                    }
                }
            }
        },
        {"$out": dataset._sample_collection_name},
    ]

    dataset._aggregate(pipeline=pipeline, attach_frames=False)


def _write_samples(dataset, src_collection):
    pipeline = src_collection._pipeline(detach_frames=True)
    pipeline.append({"$out": dataset._sample_collection_name})

    src_collection._dataset._aggregate(pipeline=pipeline, attach_frames=False)


def _add_samples(dataset, src_collection):
    pipeline = src_collection._pipeline(detach_frames=True)
    pipeline.append(
        {
            "$merge": {
                "into": dataset._sample_collection_name,
                "on": "_id",
                "whenMatched": "keepExisting",
                "whenNotMatched": "insert",
            }
        }
    )

    src_collection._dataset._aggregate(pipeline=pipeline, attach_frames=False)
