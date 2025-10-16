import { setupWorker } from 'msw/browser'
import { snapshotHandlers } from './handlers/snapshot'
import { outboundHandlers }  from './handlers/outbound'
import { taskHandlers }      from './handlers/tasks'
import { batchHandlers }     from './handlers/batches'
import { moveHandlers }      from './handlers/moves'

export const worker = setupWorker(
  ...snapshotHandlers,
  ...outboundHandlers,
  ...taskHandlers,
  ...batchHandlers,
  ...moveHandlers,
)
