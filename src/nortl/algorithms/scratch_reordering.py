from nortl.core.engine import CoreEngine


class ScratchReorderingMixin(CoreEngine):
    """The location of scratch register in the scratch map determines the size of multiplexers and the optimization potential by state merging.

    This class provides a heuristic optimization to align scratch registers with similar functions based on their origin in the code
    and their use in the states
    """
