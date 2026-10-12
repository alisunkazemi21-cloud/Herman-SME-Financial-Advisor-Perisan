# Dated package quantities — development update

A package size may change while the underlying item stays the same. The new internal calculation module uses the definition valid when each stock event happened, so an old eight-unit package is not silently treated as a new ten-unit package. Each applied factor retains its source. Missing or conflicting definitions stop the calculation from reporting a definite shortage.

This is a tested calculation step within C16, not a released catalog-editing feature. Database review, history migration and connection to the business workflow are still required. The owner interface remains deferred.
