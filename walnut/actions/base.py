from abc import ABC, abstractmethod
from typing import Literal, Dict, Any

class BaseAction(ABC):
    @abstractmethod
    def execute(self, mode: Literal['probe', 'dry_run', 'execute'], params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes the action.

        :param mode: The execution mode.
        :param params: The parameters for the action.
        :return: A dictionary with the result of the action.
        """
        pass
