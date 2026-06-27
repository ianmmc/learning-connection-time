# Aquition Process Governance Application (APGA): Views by Stage
## Document Purpose
This docuemnt is a reference for collaborative co-Development between Ian McCullough and Anthropic's Claude. This is a loose description of what each view of the new is for, what it offers, and what human reviewers can do. 

## Related documents
### Authoritative
- docs/ACQUISITION_PIPELINE.md
- docs/diagrams/acquisition_pipeline_flow.md
- docs/technical-notes/PIPELINE_GOVERNANCE_AND_STATE_2026-06.md (Scope Expansion for Application, including notes on new console functionality)

### Reference and context
- docs/technical-notes/STAGE5_FILTER_DESIGN_2026-06.md (Development of original Stage 5 Checkpoint B App)

## Console Views
- As a user, I want to be able to select different console views from a menu.

### Piepline Overview
- As a user, I want to be able to look at all nine stages at the same time and what they're processing at the moment — what district(s) are actively in the stage, what's waiting in line, and what needs human attention.
- As a user I want to be able to see percentage yields and fallout from the chained stages 1-5 by batch.
- As a user, I want to be able to start all processes.
- As a user, I want to be able to pause all processes.
- As a user, I want to be able to recoverably stop all processes.

### Stage 1: Queue - **Review Batches for Discovery**
- As a user, I want to be able to start a new batch of districts.
- As a user, I want to be able to fulfill Checkpont A functionality (when in manual review mode).
    - As a user, I want to be able to look at proposed districts and proposed schools that we propose sending into the discovery stage.
    - As a user, I want to be able to reject distrcts from inclusion in a given batch.
    - As a user, I want to be able to reject schools from a given district.
    - As a user, I want to be able to add additional schools to a given district if the districts has more schools to queue up.
- As a user, I want to be able to manually construct a batch of districts that have not yet been touched that I personally select from NCES data.
- As a user, I want to be able to re-queue up districts that have already been in the pipeline. I want to be able to action districts that have made it to stage 5 and gotten tagged with none-found or insufficient coverage. A consequence of this is that one district can exist in multiple batches with different sets of schools.
    - As a user I want to identify and select schools for the district that have alerady been submitted through discovery.
    - As a user I want to identify and select schools for the district that have not been submitted through discovery.
- As a user, I want to be able to create multiple different batches that only advance when approved to advance.
- As a user, I want all batches to be capped at no more than 12 districts. A batch can have less than 12, but no more than 12.

### Stage 2: Discovery
- As a user, I want to be able to review search query templates.
- As a user, I want to be able to propose new search query templates.
- As a user, I want to be able to see what any given search service is processing right at the moment — what district and what query. (Search service = Claude CLI WebSearch, gpt-4o-mini-search via OpenRouter, potential future servies (Bright Data, Brave API, Google Search API,etc.))
- As a user, I want insights into how effective combinations of search services and queries are at yielding bell schedule representations by the end of stage 5.

### Stage 3: Capture
I'm actually not sure if there is any truly valuable information here. Perhaps some things related to emergent URLs? Is there staff about Playwright activity that might lead to useful reflection? Or perhaps we leave this as a grayed-out option.

If we want to have something, the flow of PNGs being captured might be interesting to have and potentially spot unexpected patterns by watching? Maybe replay batches?

### Stage 4: Process
- As a user, I want insights into how effective PDF text harvesters and OCR tools are at yielding bell schedule representations by the end of stage 5.

### Stage 5: Filter - **Revie whether or not URLs have bell schedule information)**
Refer to current production state and docs/technical-notes/STAGE5_FILTER_DESIGN_2026-06.md for reference on thinking.

### Stage 6: Handoff - **Review handoff packages and assigned council configurations**
(Stage currently in design process.)
- As a user, I want to be able to initiate a handoff of district representations that have not yet gone through an extraction process.
- As a user, I want to be able to initiate a hand off of representations that have already been to an extraction council, but I want to send to a different extraction council configureation.
- As a user, I want to be able to select an alternate representation for a given URL to go to the extraction council.
    - As a user, I only want to be able to select alternate representations that either have been automatically proejcted or manually determined to have target information.
- As a user, I want representations listed in the handoff package to be organized by school district/LEA.
- As a user, I want to see the extraction council configureation that a given handoff is assigned to be routed to.
- As a user, I want to be able to override the extraction council configureation that a given handoff is assigned to be routed to.
- As a user, I want to be able to see available extraction council configurations.
- As a user, I want to be able to create new extraction council configurations based on the models available via OpenRouteer.
- As a user, I want to see default assignment criteria for different extraction council configurations.
- As a user, I want to be able to see an estimate of how much a given handoff package will cost to run through a given extraction council.
    - Note: While we can start with model pricing estimates and token estimates for representations, I may have to retrieve and submit OpenRouter log files to make these estimates more and more accurate. I'm not sure of logs are available from the API. Worth exploring.
- As a user, I want to be able to approve a handoff for dispatch to extraction.
- As a user, I want to be able to create multiple different handoff packages that only advance when approved to advance.

### Stage 7: Extract **Review Extraction Council Recommendations and Requests**
(STAGE NOT YET DESIGNED. More will come here when we get to designing tihis stage.)
- As a user, I want to be able to review requests and recommendations from the extraction council. (for example, retrieve screen-capped PNG for a given URL, retrieve PDF for a given URL, recapture a given URL, redo discovery with a different tailored search query)
- As a user, I want to be able to accept or reject requests and recommendations from the extraction council.

### Stage 8: Aggregate **Review Extraction Results by URL and Daily Instructional Minutes by Band**
This is where bell schedule information from the extraction council will be turned into daily instructional minutes by band for the district. (STAGE NOT YET DESIGNED. More will come here when we get to designing tihis stage.)
- As a user, I want to be able to re-queue a district where there are coverage gaps for a given band. As a result of this, a new batch would get created in the Stage 1 view that just has a focus on the missing bands.
- As a user, I want to be able to add a URL to a new handoff that will show up in Stage 6.
- As a user, I want to be able see the start and end times extracted for each representation OR the explicity stated instructional minutes.
    - For representations that have school start and school end times, I want to be able to see the calculated daily instructional minutes.
- As a user, I want to be able to manually edit/overwrite the start and end times from each reporesentation.
    - As a user, I want to be required to provide an explanation of why I'm overwriting the extracted values 

### Stage 9: Incorporate
This is where district level daily instructional minutes by band will be delivered to the LCT database. (STAGE NOT YET DESIGNED. More will come here when we get to designing tihis stage.)

### Settings
- As a user, I want options to toggle each human review gate between manual mode (requiring human action) and automatic mode (where the process is self-advancing and self-governing). At the time of writing, that means there would need to be toggles for Stages 1, 5, 6, 7, and 8.