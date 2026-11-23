(* Unlocated, uninitialized ST slice for the available HyPLC grammar.
   This repeats the source controller's authority assignment order but omits
   the source's located declarations, retained initialization, and timer.
   It is a translation probe, not an executable replacement PLC program. *)
PROGRAM AttleboroAuthoritySlice
VAR
  utility, mtsGen, genRun, selectorRemote, trip, resetReq, previousReset,
  resetPending, startDemand, remoteEligible, remoteStart : BOOL;
END_VAR

IF (NOT utility) OR mtsGen OR genRun THEN
  resetPending := TRUE;
ELSIF resetReq AND (NOT previousReset) THEN
  resetPending := FALSE;
END_IF;
previousReset := resetReq;
remoteEligible := utility AND (NOT mtsGen) AND (NOT genRun)
  AND (NOT resetPending) AND selectorRemote AND (NOT trip);
remoteStart := remoteEligible AND startDemand;
END_PROGRAM

CONFIGURATION Config0
  RESOURCE Res0 ON PLC
    TASK task0(INTERVAL := T#100ms,PRIORITY := 0);
    PROGRAM instance0 WITH task0 : AttleboroAuthoritySlice;
  END_RESOURCE
END_CONFIGURATION
