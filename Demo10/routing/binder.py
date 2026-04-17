from typing import Dict, Any, Optional
from services.input_compiler.models import CompiledSpecIR
from Demo10.macros.models import WorkflowMacro

class RoutingBinder:
    @staticmethod
    def bind_inputs(macro: WorkflowMacro, ir: CompiledSpecIR) -> Optional[Dict[str, Any]]:
        # map IR fields to macro input contract
        # use defaults where allowed
        # no guessing

        bound = {}
        contract = macro.input_contract

        # Available data from IR:
        # title, objective, target_path, operations[], constraints[]

        # We need to map these to macro's required_inputs
        for req in contract.required_inputs:
            if req == "instruction":
                # If IR has one operation, use its instruction
                if len(ir.operations) == 1:
                    bound[req] = ir.operations[0].instruction
                else:
                    # fallback to objective?
                    bound[req] = ir.objective
            elif req == "target":
                if ir.target_path:
                    bound[req] = ir.target_path
                elif len(ir.operations) == 1 and ir.operations[0].target:
                    bound[req] = ir.operations[0].target
                else:
                    # check defaults
                    if req in contract.default_bindings:
                        bound[req] = contract.default_bindings[req]
                    else:
                        return None # ROUTING_BINDING_MISSING
            elif req == "title":
                bound[req] = ir.title
            elif req == "objective":
                bound[req] = ir.objective
            else:
                # check default_bindings
                if req in contract.default_bindings:
                    bound[req] = contract.default_bindings[req]
                else:
                    return None # ROUTING_BINDING_MISSING

        # optional inputs
        for opt in contract.optional_inputs:
            if opt not in bound:
                if opt == "constraints":
                    bound[opt] = [c.to_dict() for c in ir.constraints]
                elif opt in contract.default_bindings:
                    bound[opt] = contract.default_bindings[opt]

        return bound
