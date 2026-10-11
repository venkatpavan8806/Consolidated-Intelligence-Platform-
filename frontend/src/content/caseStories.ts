// Scripted walkthroughs for the demo cases, shown on the "Case Demo" tab.
//
// Everything here is explanation, not data: the page pulls the live record
// counts and live lead counts from the API, and this file only says what each
// record type contributes to THIS case and what each detector step means. If a
// case_id has no entry here, the Case Demo page still works -- it falls back to
// the live evidence and module status with a generic explanation.

export interface StoryStep {
  title: string;
  body: string;
  // Lead types this step produces; the page shows each one's live count and
  // links to it, or says it is held back until its case type is confirmed.
  leadTypes?: string[];
}

export interface CaseStory {
  headline: string;
  situation: string;
  // evidence-source key (see backend app/evidence/summary.py) -> what that
  // record type contributes in this case.
  connects: Record<string, string>;
  // Shown when the case has no relationship graph worth looking at.
  graphNote?: string;
  steps: StoryStep[];
  humanDecision: string;
  tryIt?: { text: string; caseType: string };
  limits: string[];
}

const HUMAN_DECIDES =
  'Nothing above is an accusation. Each finding is a lead with the exact source records behind it. ' +
  'An investigator marks it Useful, Already known or Wrong person, and every query and decision is written to the tamper-evident audit chain. ' +
  'The platform never scores a person and never decides guilt.';

export const CASE_STORIES: Record<string, CaseStory> = {
  C001: {
    headline: 'A digital fraud ring: money moved through layers of accounts while phones were swapped to hide the trail.',
    situation:
      'Police hold FIRs naming accused people with their phones and bank accounts, plus intelligence notes about a suspected SIM swap and a layering pattern. ' +
      'Separately the platform holds raw call records and bank transfers. Cross-checking every call and transfer against those notes by hand is slow and easy to get wrong. The platform does it in one pass.',
    connects: {
      FIR: 'Names, phone numbers and account numbers of accused and witnesses: the starting points of the graph. Officers are recognised by role and kept out of every ranking.',
      INTEL: 'A surveillance report flags a phone that went quiet just as a new one appeared; an intelligence-unit report describes a layering pattern. These are hints the platform then tests against the raw data.',
      CDR: 'Who called whom, when, and on which handset (IMEI). The raw material for spotting burner SIMs.',
      TXN: 'Every transfer between accounts: the money trail that layering and call-then-transfer patterns are found in.',
      IDINDEX: 'Phones, accounts and vehicles that recur across FIRs. This is how a link to another case can surface.',
    },
    steps: [
      {
        title: 'Read the text and resolve who is who',
        body:
          'The platform reads every FIR and report, pulls out names, phones and accounts, and merges different spellings of the same person. ' +
          'It never merges two people on name alone: an ambiguous pair goes to the Review Queue for a human.',
      },
      {
        title: 'Join calls, transfers and FIR mentions into one graph',
        body: 'Calls, transfers and FIR mentions become a single relationship map. Open the Graph tab to see it; each dot carries its short initials.',
      },
      {
        title: 'Spot a burner-SIM swap',
        body:
          'One phone goes silent; a day later a new number takes over most of its contacts, and the two never call each other. ' +
          'The IMEI leads add device-level evidence: the same physical handset was used with both SIMs. A shared handset can also be innocent, so the lead says so and asks for a human check.',
        leadTypes: ['BURNER_ROTATION', 'IMEI_MSISDN_MAPPING', 'IMEI_CORROBORATED_BURNER_SWAP'],
      },
      {
        title: 'Uncover mule-account layering',
        body: 'Many small senders feed a few intermediate accounts, which feed a final account, so that no single transfer looks suspicious. The platform finds the funnel shape.',
        leadTypes: ['MULE_LAYERING'],
      },
      {
        title: 'Catch a call followed by a large transfer',
        body: 'A call, then within minutes a transfer far larger than this dataset’s normal size, between accounts tied to the same phones: the shape of a phone-solicited fraud.',
        leadTypes: ['CALL_BEFORE_TRANSFER'],
      },
      {
        title: 'Find quiet go-betweens',
        body: 'Accounts that bridge otherwise separate groups with very few connections of their own: a broker, not just a busy hub. This check applies to every case type.',
        leadTypes: ['BROKER_BRIDGE'],
      },
    ],
    humanDecision: HUMAN_DECIDES,
    tryIt: {
      text:
        'The same phone number appears in two separate FIRs, which points to a different kind of case. On Overview press “Re-run classifier”: it suggests Organized Crime. ' +
        'Until you press Confirm, that module stays off and its lead is held back. Confirm it, then open Leads and watch the cross-case link appear.',
      caseType: 'ORGANIZED_CRIME',
    },
    limits: [
      'A pattern is a strong hint, not proof of who did what.',
      'A handset shared across two numbers can be a family phone: the lead says so rather than assuming a swap.',
      'Raw counts and amounts are real; any threshold used is shown on the lead itself.',
    ],
  },

  C002: {
    headline: 'Missing women and unidentified bodies: lining up registers that no one has compared.',
    situation:
      'Families have reported women missing from the Sonepur corridor, and unidentified bodies have been recorded. The paperwork sits in separate registers: missing-person reports, unidentified-body (UIDB) records, post-mortem reports and DNA samples. ' +
      'The platform lines them up and checks whether the handling rules were followed.',
    connects: {
      FIR: 'A missing-person complaint (a woman last seen boarding a bus near Sonepur Junction) and a camera sighting of a vehicle tied to a phone number.',
      INTEL: 'A surveillance report of a suspected recruiter approaching young women near the junction, and a state-intelligence advisory of trafficking-linked movement on the corridor.',
      CDR: 'Who the suspected recruiter’s phone and the phones around it called: the contact network you can see in the Graph tab.',
      MISSING: 'Each missing person described in standard terms: sex, age range, height, clothing, district.',
      UIDB: 'Each unidentified body described in the same terms, so the two registers can be compared.',
      POSTMORTEM: 'The medical examination behind each body record.',
      DNA: 'DNA samples with when they were collected and dispatched, who examined them, and what the lab concluded.',
      IDINDEX: 'Phone numbers that recur across the FIRs and reports.',
    },
    steps: [
      {
        title: 'Match bodies to missing-person reports',
        body:
          'Each unidentified body is compared with each missing-person report on sex, age range, height, clothing colour and district. ' +
          'A match is only ever a candidate identification, never a confirmed one, following the national ZIPNET approach.',
        leadTypes: ['UIDB_MISSING_PERSON_CANDIDATE_MATCH'],
      },
      {
        title: 'Catch a match the case file ignored',
        body: 'One body record already points to a missing-person report, yet that case is still shown as open: the match exists on paper and nobody acted on it.',
        leadTypes: ['UIDB_IGNORED_ZIPNET_MATCH'],
      },
      {
        title: 'Check the evidence-handling rules',
        body:
          'A body with a post-mortem but no DNA sample is a one-time, perishable opportunity lost. A DNA sample sent to the lab later than the court-directed 48 hours is flagged. ' +
          'And an inconclusive, unexamined DNA result relied on alone as the basis of an identification is flagged too.',
        leadTypes: ['UIDB_UNSAMPLED_BODY', 'UIDB_LATE_DNA_DISPATCH', 'UIDB_WEAK_DNA_CONCLUSION_RELIED_ALONE'],
      },
    ],
    humanDecision:
      'These are candidate identifications and procedural gaps for the investigating officer and the family. Confirming who a person is needs a proper identification process; ' +
      'the platform never declares an identity. ' + HUMAN_DECIDES,
    limits: [
      'Matching uses recorded descriptions only. There is no photograph or face matching, by design.',
      'The Graph tab shows the phone network around the suspected recruiter, but this release runs no trafficking-chain detector on it. The findings here come from the physical records.',
    ],
  },

  C003: {
    headline: 'Two drug seizures where the paperwork decides the case: one done by the book, one not.',
    situation:
      'A vehicle was intercepted near the Sonepur bypass with suspected heroin, then a follow-up raid recovered suspected charas from a rented storage unit linked to the same accused. ' +
      'In narcotics cases the procedure is evidence: if sampling, sealing, magistrate certification or lab handling went wrong, the seizure can be thrown out.',
    connects: {
      FIR: 'The two police narratives: the interception on the bypass and the follow-up raid.',
      PROPERTY: 'The two seizure registers: what was seized, when, where, and in front of which witnesses.',
      PROPERTY_ITEM: 'Each packet or exhibit, with its weights and seals.',
      NDPS: 'The lab Test Memo (Form-6) for each seizure: sample drawn, weights, seals, magistrate certification.',
      CUSTODY: 'Every handover from the evidence store to the lab to the court.',
    },
    graphNote: 'This case has almost no relationship graph, by design. It is paperwork, not a network, so the value is in the checks below.',
    steps: [
      {
        title: 'Read each seizure like a checklist',
        body:
          'Each Test Memo is checked against the NDPS sampling rules: sample size, how many identical packages were bunched into one lot, whether seals and weights match, ' +
          'whether copies were made in triplicate, whether a magistrate certified the sampling, and whether events happened in the right order.',
      },
      {
        title: 'Flag what breaks the rules',
        body:
          'The heroin seizure passes with zero flags, shown as clean rather than noisy. The charas seizure raises several separate flags at once, such as a missing magistrate certification, ' +
          'a seal and weight mismatch, and a sample drawn before the seizure. The lead lists each one.',
        leadTypes: ['NDPS_COMPLIANCE'],
      },
    ],
    humanDecision:
      'The platform lists procedural gaps. Whether they weaken the case is a legal judgement for the prosecutor and the court. ' + HUMAN_DECIDES,
    limits: [
      'A few tolerances, such as the weight-mismatch allowance, are our own defaults, not official figures. The code labels them as such.',
      'The quiet result on the first seizure matters as much as the noisy one: a checker that flags everything is useless.',
    ],
  },

  C004: {
    headline: 'A run of thefts and chain-snatchings: matching stolen property to recovered property, and spotting a repeat pair.',
    situation:
      'In Ring Bazaar a motorcycle, a scooter, a laptop and a gold chain were reported stolen, and two chain-snatchings by the same pair on a motorcycle followed. ' +
      'Stolen-property reports sit in one register and property recovered later sits in another; the platform connects them.',
    connects: {
      FIR: 'Theft complaints with registration, chassis and engine numbers and serial numbers, and the two snatching FIRs naming two accused.',
      PROPERTY: 'What was recovered later, by seizure register.',
      PROPERTY_ITEM: 'Each recovered vehicle and item with its identifiers and value.',
      MO: 'Modus-operandi forms (NCRB IIF-II): how each crime was committed: method, vehicle used, disguise, place, property.',
      CHARGESHEET: 'Earlier charge-sheets, used later for the syndicate test.',
      IDINDEX: 'Phones and vehicle numbers that recur across FIRs, including from other states.',
    },
    steps: [
      {
        title: 'Match stolen vehicles to recovered ones',
        body:
          'Reported-stolen vehicles are compared with recovered vehicles on registration, chassis and engine numbers: two of the three, partial numbers allowed, the rule NCRB’s Vahan Samanvay system uses. ' +
          'One recovered scooter matches on chassis while its other numbers disagree, which is consistent with a re-identified vehicle.',
        leadTypes: ['ROBBERY_VEHICLE_LINK'],
      },
      {
        title: 'Match other property',
        body: 'A laptop with the same serial number is an exact link. A gold chain matches only by description and a value within a tolerance, so it is shown as a weaker candidate, never a link.',
        leadTypes: ['ROBBERY_PROPERTY_MATCH'],
      },
      {
        title: 'Find a crime series',
        body:
          'Two snatching FIRs 30 days apart match on five of the six modus-operandi fields and share two accused: a candidate series. A burglary with a different method is deliberately left out.',
        leadTypes: ['ROBBERY_MO_SERIES_S112_CANDIDATE'],
      },
      {
        title: 'Widen the lens to organised crime',
        body:
          'The same phones and a vehicle number turn up in other FIRs, including one from another state, and the accused are tied to charge-sheets. ' +
          'That is a different case type, so these leads stay held back until an investigator confirms Organized Crime for this case.',
        leadTypes: [
          'INTERSTATE_IDENTIFIER_LINKAGE_ALERT', 'CROSS_CASE_IDENTIFIER_LINK',
          'SHARED_INFRASTRUCTURE_LINK', 'SYNDICATE_S111_THRESHOLD_MET',
        ],
      },
    ],
    humanDecision: HUMAN_DECIDES,
    tryIt: {
      text:
        'On Overview press “Re-run classifier”: Organized Crime is suggested, with the evidence listed. Confirm it, then open Leads: ' +
        'the cross-case, shared-infrastructure and syndicate leads appear. Reject it instead and they stay off.',
      caseType: 'ORGANIZED_CRIME',
    },
    limits: [
      'A candidate series is not a proven series: a court decides that.',
      'A value-based property match is weaker than a serial-number match, and is labelled as a candidate.',
    ],
  },

  C005: {
    headline: 'A raid recovers property: tying it back to the thefts, and watching how long it sits in storage.',
    situation:
      'A raid recovered property that may belong to the thefts in the Ring Bazaar case. This case holds only the recovery paperwork: no FIRs, calls or transfers. ' +
      'It shows how one set of physical records can connect two cases.',
    connects: {
      PROPERTY: 'The recovery registers from the raid.',
      PROPERTY_ITEM: 'Each recovered item with its identifiers (chassis, serial number) and estimated value.',
      CUSTODY: 'Storage and court-disposal events for the recovered items, if any.',
    },
    graphNote: 'There is no relationship graph for this case: it is purely physical paperwork, and the value is in the matches below.',
    steps: [
      {
        title: 'Link recovered items back to the thefts',
        body: 'The same matching as in the theft case, run from the recovery side: vehicles on registration, chassis and engine, and other items on serial number or description and value.',
        leadTypes: ['ROBBERY_VEHICLE_LINK', 'ROBBERY_PROPERTY_MATCH'],
      },
      {
        title: 'Watch the storage clock',
        body:
          'Recovered property that has sat in the evidence store with no court-disposal record for more than 90 days (our default review point) is flagged as a possible lapse of the interim-custody rules. ' +
          'Items that are properly handled stay silent.',
        leadTypes: ['ROBBERY_LINGERING_PROPERTY'],
      },
    ],
    humanDecision: HUMAN_DECIDES,
    limits: [
      'The 90-day review point is our own default, not an official figure: the research did not find one.',
      'A match says two records describe the same item; whether it is the same item is for the investigator to confirm.',
    ],
  },

  C006: {
    headline: 'A death in police custody: the records disagree with each other, and with the rules they should follow.',
    situation:
      'A detainee, Manoj Kumar, was found dead in the lockup at the Riverside Godown facility, and a companion assault victim, Ram Lal, was examined too. ' +
      'The inquest, post-mortem, medico-legal records, a phone-tower trail and forensic exhibits all exist, and several contradict each other or break procedure.',
    connects: {
      FIR: 'The narrative of the custodial death.',
      INQUEST: 'The inquest: who was present, what injuries were recorded, and when the death was intimated.',
      POSTMORTEM: 'The autopsy: the injury list and the time-of-death fields.',
      MLC: 'Medico-legal records classifying each injury as simple or grievous, with follow-up days.',
      TOWER: 'Cell-tower pings of a phone near the scene around the time of death.',
      FORENSIC: 'Fingerprint and ballistics matches that link exhibits here to a cold case (C007), plus a DNA result that is only inconclusive.',
    },
    steps: [
      {
        title: 'Check the inquest against the rules',
        body: 'The law requires two respectable inhabitants to be present at an inquest, and a custodial death to be intimated promptly. This inquest recorded too few witnesses and intimated the death late.',
        leadTypes: ['INQUEST_WITNESS_VIOLATION', 'CUSTODIAL_DEATH_INTIMATION_VIOLATION'],
      },
      {
        title: 'Cross-check the inquest against the post-mortem',
        body: 'The post-mortem lists a ligature mark on the neck that the inquest does not, and key time-of-death fields (rectal temperature, rigor mortis timing) were left blank.',
        leadTypes: ['INQUEST_PM_INJURY_MISMATCH', 'POSTMORTEM_MISSING_TIMING_FIELDS'],
      },
      {
        title: 'Re-check injury classifications',
        body: 'One medico-legal record calls an injury grievous but shows one day of follow-up; another calls one simple but shows 25 days. Each is worth re-checking. The platform never reclassifies an injury itself.',
        leadTypes: ['MLC_CLASSIFICATION_INCONSISTENCY'],
      },
      {
        title: 'Link to other cases through forensics',
        body:
          'A fingerprint hit in the national fingerprint database ties an exhibit here to the cold case. A ballistics link is shown differently, as an examiner’s opinion, because India has no networked ballistics database. ' +
          'And a DNA result that is only “inconclusive” but treated as a positive match is flagged.',
        leadTypes: ['FORENSIC_FINGERPRINT_MATCH', 'FORENSIC_BALLISTICS_EXAMINER_ASSERTED', 'FORENSIC_CONFIDENCE_MISUSE'],
      },
      {
        title: 'Test the phone-tower evidence',
        body:
          'A phone pinged near the godown within minutes of the recorded time of death, which is a strong lead. But the tower record has no section 63 / 65B(4) certificate, so it is a lead needing certification, never usable proof as it stands.',
        leadTypes: ['SPATIOTEMPORAL_TOWER_CORRELATION', 'UNCERTIFIED_TOWER_EVIDENCE'],
      },
    ],
    humanDecision:
      'The platform points at inconsistencies and rule breaches; it does not decide cause of death or responsibility. ' + HUMAN_DECIDES,
    limits: [
      'A ballistics link is an examiner’s opinion, not a database hit, and must be verified independently.',
      'An uncertified tower record is a lead only. It cannot be used as proof until certified.',
    ],
  },

  C007: {
    headline: 'A cold case reopened from the outside: its only strong evidence arrives from another case.',
    situation:
      'An earlier unsolved assault near the Riverside Godown, with no arrest. On its own it holds almost nothing: a single FIR. ' +
      'Its value appears only when exhibits from this case are matched against the custodial-death case.',
    connects: {
      FIR: 'The one-paragraph FIR for the unsolved assault.',
      FORENSIC: 'Forensic matches that reach across to the custodial-death case (C006).',
    },
    graphNote: 'The graph is a single point, as expected. The connection here is between cases, not between people in this case.',
    steps: [
      {
        title: 'Let another case reopen this one',
        body:
          'A fingerprint from this case’s exhibit matches one in the custodial-death case through the national fingerprint database, and a ballistics examiner opines a link between the two exhibits. ' +
          'Both cases now point at each other; the ballistics link is clearly marked as an opinion, not a database hit.',
        leadTypes: ['FORENSIC_FINGERPRINT_MATCH', 'FORENSIC_BALLISTICS_EXAMINER_ASSERTED'],
      },
    ],
    humanDecision: HUMAN_DECIDES,
    limits: [
      'A fingerprint hit links exhibits; it does not by itself say who was present or when.',
      'The ballistics link must be verified independently: there is no networked ballistics database to check it against.',
    ],
  },

  C008: {
    headline: 'The control case: a stabbing death investigated by the book, where the platform stays quiet.',
    situation:
      'A stabbing death at a home in Lakeview Colony, investigated with full procedural compliance. This case exists to show the opposite of the custodial-death case: ' +
      'when procedure is followed, the same checks fire nothing.',
    connects: {
      FIR: 'The complaint reporting the death.',
      INQUEST: 'A compliant inquest.',
      POSTMORTEM: 'A complete post-mortem with its timing fields filled in.',
      MLC: 'A consistent medico-legal record.',
      TOWER: 'A cell-tower ping of a phone near the colony gate, with its legal certificate attached.',
      FORENSIC: 'A DNA report comparing crime-scene material with the accused’s reference sample.',
    },
    steps: [
      {
        title: 'Run the same checks as the custodial-death case',
        body: 'Every inquest, post-mortem and medico-legal check runs here too, and none of them fire. A tool that flags everything is useless; staying quiet on a compliant file is what makes the flags elsewhere credible.',
      },
      {
        title: 'Report what is actually there',
        body:
          'A DNA report matches the crime-scene exhibit to the accused’s reference sample, and a phone pinged at the colony gate within half an hour of the recorded time of death. ' +
          'This time the tower record is certified, so no warning is attached.',
        leadTypes: ['FORENSIC_DNA_MATCH', 'SPATIOTEMPORAL_TOWER_CORRELATION'],
      },
    ],
    humanDecision: HUMAN_DECIDES,
    limits: [
      'A DNA match shows that two exhibits correspond. It does not by itself establish who was present, or when.',
      'A phone ping near a place is a lead: it does not by itself show who was carrying the phone.',
    ],
  },

  C009: {
    headline: 'Separate small FIRs that together look like one interstate vehicle-theft syndicate.',
    situation:
      'Several accused appear across FIRs from different police units and states: a coordinator working from outside the state, a joint interstate raid, and old records kept for criminal-history reference. ' +
      'Each FIR alone looks like a small case. Together they look like a syndicate.',
    connects: {
      FIR: 'Four FIRs from the Records Cell, the Neighbouring State Task Force and the Interstate Crime Cell.',
      IDINDEX: 'An index of every phone, bank account and vehicle number across all FIRs: the key that links cases.',
      CHARGESHEET: 'The accused’s charge-sheets, counted for the “continuing unlawful activity” test.',
    },
    steps: [
      {
        title: 'Index every identifier across all FIRs',
        body: 'Phones, accounts and vehicle registrations are indexed across every FIR. Accused-ID numbers are deliberately left out, so two people are never linked just for sharing a number type.',
      },
      {
        title: 'Link cases through shared identifiers',
        body: 'The same phone in two FIRs is a link. The same phone in three FIRs across two police stations clears the interstate bar and becomes an alert.',
        leadTypes: ['CROSS_CASE_IDENTIFIER_LINK', 'INTERSTATE_IDENTIFIER_LINKAGE_ALERT'],
      },
      {
        title: 'Find shared infrastructure',
        body: 'Different accused tied to the same phone or vehicle suggest a common cell, even if they were never charged together.',
        leadTypes: ['SHARED_INFRASTRUCTURE_LINK'],
      },
      {
        title: 'Test the legal threshold',
        body:
          'Charge-sheets are counted per syndicate, not per person, against the BNS section 111 / MCOCA “continuing unlawful activity” threshold. ' +
          'A lone accused with no associates never forms a syndicate on their own.',
        leadTypes: ['SYNDICATE_S111_THRESHOLD_MET'],
      },
      {
        title: 'Pull in the robbery series behind it',
        body: 'The earlier snatching series from Ring Bazaar is a Robbery/Theft finding. It stays held back here until an investigator confirms Robbery/Theft for this case.',
        leadTypes: ['ROBBERY_MO_SERIES_S112_CANDIDATE'],
      },
    ],
    humanDecision:
      'Whether a group is a syndicate in law is for a court. The platform shows the evidence and the count. ' + HUMAN_DECIDES,
    tryIt: {
      text:
        'On Overview press “Re-run classifier”: Robbery/Theft is suggested for this case. Until you confirm it, the snatching-series lead is held back. Confirm it and watch it join the Leads tab.',
      caseType: 'ROBBERY_THEFT',
    },
    limits: [
      'The ten-year window and the per-syndicate count follow the judgments cited on the lead; they are applied as written, not tuned.',
      'A shared phone number is a link, not proof of membership in a group.',
    ],
  },
};

// Used when a case has no scripted walkthrough: the page still shows the live
// evidence and module status, with this generic explanation.
export const GENERIC_STORY: CaseStory = {
  headline: 'What this case connects, and what the platform found.',
  situation:
    'This case has no scripted walkthrough yet. Below is exactly what the platform holds for it and which detector modules are switched on, taken live from the data.',
  connects: {},
  steps: [],
  humanDecision: HUMAN_DECIDES,
  limits: ['Every finding is a lead for a human to verify; none is a verdict.'],
};
