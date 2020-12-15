"""
FiftyOne quickstart.

| Copyright 2017-2020, Voxel51, Inc.
| `voxel51.com <https://voxel51.com/>`_
|
"""
import os

import fiftyone as fo
import fiftyone.core.context as focx
import fiftyone.core.session as fos
import fiftyone.zoo as foz


_EXIT = os.environ.get("FIFTYONE_EXIT", False)


def quickstart(
    interactive=True, video=False, port=5151, remote=False, desktop=False
):
    """Runs the FiftyOne quickstart.

    This method loads an interesting dataset from the Dataset Zoo, launches the
    App, and prints some suggestions for exploring the dataset.

    Args:
        interactive (True): whether to launch the session asynchronously and
            return a session
        video (False): whether to launch a video dataset
        port (5151): the port number to serve the App
        remote (False): whether this is a remote session, and opening the App
            should not be attempted
        desktop (False): If `True`, the session will launch the desktop App.
            The desktop App package must be installed (fiftyone-desktop),
            if so. The `FIFTYONE_DESKTOP_WINDOW=true` environment variable can
            be used as a persistent desktop setting. DOES NOT apply to notebook
            contexts (e.g. Jupyter), use :meth:`Session.show` instead.

    Returns:
        If ``interactive`` is ``True``, a tuple is returned containing:

        -   dataset: the :class:`fiftyone.core.dataset.Dataset` that was loaded
        -   session: the :class:`fiftyone.core.session.Session` instance for
            the App that was launched

        If ``interactive`` is ``False``, ``None`` is returned
    """
    if video:
        return _video_quickstart(interactive, port, remote, desktop)
    else:
        return _quickstart(interactive, port, remote, desktop)


def _quickstart(interactive, port, remote, desktop):
    dataset = foz.load_zoo_dataset("quickstart")
    session = fos.launch_app(
        dataset=dataset, port=port, remote=remote, desktop=desktop
    )

    # @todo improve readability of stdout when launching remote sessions

    if interactive:
        print(_QUICKSTART_GUIDE % (_FILTER_DETECTIONS_IN_PYTHON))
        return dataset, session

    print(_QUICKSTART_GUIDE % (""))
    if not _EXIT:
        session.wait()

    return None


def _video_quickstart(interactive, port, remote, desktop):
    dataset = foz.load_zoo_dataset("quickstart-video")
    session = fos.launch_app(
        dataset=dataset, port=port, remote=remote, desktop=desktop
    )
    instructions = _VIDEO_QUICKSTART_GUIDE

    # @todo improve readability of stdout when launching remote sessions
    if interactive:
        print(instructions)
        return dataset, session

    print(instructions)
    if not _EXIT:
        session.wait()

    return None


_QUICKSTART_GUIDE = """
Welcome to FiftyOne!

This quickstart downloaded a dataset from the Dataset Zoo and created a
session, which is a connection to an instance of the App.

The dataset contains ground truth labels in a `ground_truth` field and
predictions from an off-the-shelf detector in a `predictions` field. It also
has a `uniqueness` field that indexes the dataset by visual uniqueness.

Here are some things you can do to explore the dataset:


(a) Double-click on an image to explore its labels in more detail


(b) Sort the dataset by uniqueness:

    - Click `add stage`
    - Select the `SortBy` stage
    - Select the `uniqueness` field

    Try setting `reverse` to `True` to show the *most unique* images first.
    Try setting `reverse` to `False` to show the *least unique* images first.


(c) Filter predictions by confidence

    The predictions field is noisy, but you can use FiftyOne to filter them!

    In the display options menu on the left, click on the `v` caret to the
    right of the `predictions` field to open a label filter. Drag the
    confidence slider to only include predictions with confidence at least 0.8!
%s

Resources:

-   Using the App: https://voxel51.com/docs/fiftyone/user_guide/app.html
-   Dataset Zoo:   https://voxel51.com/docs/fiftyone/user_guide/dataset_creation/zoo.html
"""


_FILTER_DETECTIONS_IN_PYTHON = """
    You can also filter the detections from Python. Assuming you ran the
    quickstart like this::

        import fiftyone as fo

        dataset, session = fo.quickstart()

    Then you can filter the predictions by creating a view:

        from fiftyone import ViewField as F

        # Create a view that only contains predictions whose confidence is at
        # least 0.8
        high_conf_view = dataset.filter_detections(
            "predictions", F("confidence") > 0.8
        )

        # Open the view in the App!
        session.view = high_conf_view
"""


_VIDEO_QUICKSTART_GUIDE = """
Welcome to FiftyOne!

This quickstart downloaded a dataset from the Dataset Zoo and created a
session, which is a connection to an instance of the App.

The dataset contains small video segments with dense object detections
generated by human annotators.

Here are some things you can do to explore the dataset:


(a) Hover over the videos in the grid view to play their contents

(b) Use the display options menu to toggle and filter detections

(c) Double-click on a video to open the expanded view, and use the video player
    to scrub through the frames


Resources:

-   Using the App: https://voxel51.com/docs/fiftyone/user_guide/app.html
-   Dataset Zoo:   https://voxel51.com/docs/fiftyone/user_guide/dataset_creation/zoo.html
"""
