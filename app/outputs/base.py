from abc import ABC, abstractmethod
from typing import Any

from app.deals import SelectedDeal


class OutputAdapter(ABC):
    @abstractmethod
    async def publish(self, deals: list[SelectedDeal]) -> Any:
        raise NotImplementedError
