import pytest
import torch
from _ddp_thunder import DDPThunderStrategy

from lightning import Fabric
# from tests.tests_fabric.helpers.runif import RunIf


# @RunIf(min_cuda_gpus=2, thunder=True, standalone=True)
@pytest.mark.parametrize("strategy", ["ddp", DDPThunderStrategy()])
def test_no_backward_sync(strategy):
    fabric = Fabric(devices=2, accelerator="cuda", strategy=strategy)
    fabric.launch()

    model = torch.nn.Linear(1, 1, bias=False, device=fabric.device)
    x = torch.randn(1, 1, device=fabric.device)
    model = fabric.setup(model)

    # 6 iters, 3 grad accumulation iters
    for i, enabled in enumerate((True, True, False, True, True, False), 1):
        x = torch.tensor([i * (fabric.local_rank + 1)], device=fabric.device, dtype=torch.float32)

        with fabric.no_backward_sync(model, enabled):
            y = model(x)
            y.backward()
        if not enabled:
            # Math for the first 3 iters
            #
            # DistributedDataParallel
            # (1*1+2*1+3*1 + 1*2+2*2+3*2) / 2       = 9
            #  ^^^^^^^^^^^   ^^^^^^^^^^^  ^^^
            #  rank0         rank1        allreduce
            #
            # thunder.distributed.ddp
            # ((1*1+2*1) + (1*2+2*2)) / 2        + (3*1 + 3*2)  / 2        = 9
            #   ^^^^^^^     ^^^^^^^   ^^^           ^^^   ^^^   ^^^
            #   rank0       rank1     allreduce1    rank0 rank1 allreduce2
            assert model.weight.grad.item() == (9.0 if i == 3 else 22.5)
            model.weight.grad = None
