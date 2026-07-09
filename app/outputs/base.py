from abc import ABC, abstractmethod

from app.deals import SelectedDeal


class OutputAdapter(ABC):
    @abstractmethod
    async def publish(self, deals: list[SelectedDeal]) -> None:
        raise NotImplementedError
