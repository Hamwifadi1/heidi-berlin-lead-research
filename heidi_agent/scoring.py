"""Transparent evidence-driven lead fit; geography and management are prerequisites."""
WEIGHTS = {
    'Residential / WEG management':30,
    'Managed portfolio size':25,
    'Heating / billing relevance':20,
    'Portfolio complexity':15,
    'Digital / operational fit':10,
}


def best_facts(rows):
    result={}
    for fact in rows:
        result.setdefault(fact['field'],dict(fact))
    return result


def qualification(facts):
    ber=facts.get('berlin_presence',{}).get('value') == 'Yes'
    manages=(facts.get('residential_management',{}).get('value')=='Yes' or
             facts.get('weg_management',{}).get('value')=='Yes')
    if not ber:
        return 'Needs Berlin Evidence'
    if not manages:
        return 'Needs Management Evidence'
    return 'Qualified (provisional)'


def score_company(facts):
    """Unknown inputs add no points; scores are only shown if minimum eligibility is evidenced."""
    qual=qualification(facts)
    pieces={}
    breakdown=[]
    def note(key,points,explanation,field=''):
        f=facts.get(field,{})
        breakdown.append((key,points,WEIGHTS[key],explanation,f.get('source_url','')))
        pieces[key]=points

    housing=(facts.get('residential_management',{}).get('value')=='Yes' or
             facts.get('weg_management',{}).get('value')=='Yes')
    note('Residential / WEG management',30 if housing else 0,
         'Documented WEG or residential management' if housing else 'Not evidenced',
         'residential_management' if facts.get('residential_management',{}).get('value')=='Yes' else 'weg_management')
    units=facts.get('portfolio_units',{}).get('value')
    count=int(units) if units and str(units).isdigit() else None
    size_score=(25 if count>=1000 else 18 if count>=300 else 12 if count>=100 else 5) if count else 0
    note('Managed portfolio size',size_score,
         f'{count} explicitly published managed units' if count else 'Managed units not published/verified',
         'portfolio_units')
    heat=facts.get('heating_billing_relevance',{}).get('value')=='Yes'
    note('Heating / billing relevance',20 if heat else 0,
         'Published relevant billing or metering service' if heat else 'Not evidenced',
         'heating_billing_relevance')
    comp=facts.get('portfolio_complexity',{}).get('value')=='Yes'
    note('Portfolio complexity',15 if comp else 0,
         'Published multi-building or diverse-portfolio indication' if comp else 'Not evidenced',
         'portfolio_complexity')
    digi=facts.get('digital_operations_fit',{}).get('value')=='Yes'
    note('Digital / operational fit',10 if digi else 0,
         'Documented digital/operational services' if digi else 'Not evidenced',
         'digital_operations_fit')
    score=sum(pieces.values()) if qual=='Qualified (provisional)' else None
    priority=('High' if score>=75 else 'Medium' if score>=50 else 'Low') if score is not None else 'Unscored'
    key_fields=['berlin_presence','residential_management','weg_management','portfolio_units',
                'heating_billing_relevance','portfolio_complexity','digital_operations_fit']
    known=sum(1 for field in key_fields if field in facts)
    completeness=round(100*known/len(key_fields))
    return {'qualification':qual,'score':score,'priority':priority,
            'completeness':completeness,'breakdown':breakdown}
