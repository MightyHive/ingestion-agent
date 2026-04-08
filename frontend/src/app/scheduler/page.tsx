"use client"

import {useConnectorStore} from "@/lib/stores/connectorStore"
import ScheduleFrequencyCard from "@/components/scheduler/ScheduleFrequencyCard"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"

export default function SchedulerPage() {

return (
    <div>
        <ScheduleFrequencyCard />
        <Alert>
            <AlertTitle>Work in progress...</AlertTitle>
            <AlertDescription>
                We are working on the scheduler. Please check back later.
            </AlertDescription>
        </Alert>
     </div>
)
};
