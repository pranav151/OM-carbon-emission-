"""Presentation helpers; metrics derive from verified daily execution records."""
import html
import plotly.graph_objects as go
import streamlit as st
from .sustainability import percent_reduction

GREEN, NAVY, BLUE = '#62edc6', '#eaf7fc', '#80b7ff'
POLICIES = {'baseline':'Baseline · moving average','selected_ml':'Selected ML + cost planning','carbon_aware':'Selected ML + carbon planning'}

def totals(daily,policy,months):
    frame=daily[daily.month.isin(months)]
    base=frame[frame.policy.eq('baseline')]
    selected=frame[frame.policy.eq(policy)]
    if set(base.date)!=set(selected.date) or base.empty:
        raise ValueError('Policies must cover identical dates')
    b,c=base.select_dtypes('number').sum(),selected.select_dtypes('number').sum()
    fill=c.served_units/c.actual_units if c.actual_units else 1.0
    bfill=b.served_units/b.actual_units if b.actual_units else 1.0
    return {'cost':c.cost,'baseline_cost':b.cost,'emissions':c.emissions_kg,'baseline_emissions':b.emissions_kg,
        'carbon_saved':b.emissions_kg-c.emissions_kg,'cost_saved':b.cost-c.cost,
        'carbon_pct':percent_reduction(b.emissions_kg,c.emissions_kg),'cost_pct':percent_reduction(b.cost,c.cost),
        'fill_rate':fill,'baseline_fill_rate':bfill,'qualified':fill>=max(.95,bfill)-1e-8,
        'unmet':c.unmet_units,'actual':c.actual_units,'routes':int(c.routes),'distance':c.distance_km}

def card(label,value,detail,tone='neutral'):
    st.markdown(f'<div class="kpi kpi-{tone}"><div class="kpi-label">{html.escape(label)}</div><div class="kpi-value">{html.escape(value)}</div><div class="kpi-detail {tone}">{html.escape(detail)}</div><div class="kpi-accent"></div></div>',unsafe_allow_html=True)

def chart_style(fig,height=340):
    fig.update_layout(template='plotly_dark',paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',height=height,
        font=dict(family='Inter, system-ui, sans-serif',color='#abc5d5',size=11),margin=dict(l=12,r=24,t=45,b=25),
        legend=dict(orientation='h',y=1.18,x=0,font=dict(size=10)),hovermode='x unified',
        hoverlabel=dict(bgcolor='#16364a',bordercolor='#6aaba9',font_color='#effbff'),
        colorway=[GREEN,BLUE,'#b6a2f4','#ffbf9d'],barcornerradius=7)
    fig.update_xaxes(showgrid=False,tickfont=dict(color='#9bb9ca'),linecolor='#a0cee71a',automargin=True)
    fig.update_yaxes(gridcolor='#afd8ee10',zerolinecolor='#a5d8ee2e',tickfont=dict(color='#9bb9ca'),automargin=True)
    return fig

def month_chart(monthly,policy,months,metric,ylabel):
    data=monthly[monthly.month.isin(months)]
    fig=go.Figure()
    for p,color in [('baseline','#55758d'),(policy,GREEN)]:
        rows=data[data.policy.eq(p)].sort_values('month')
        fig.add_bar(x=rows.month,y=rows[metric],name=POLICIES[p],marker_color=color,hovertemplate='%{x}<br>%{y:,.2f}<extra>%{fullData.name}</extra>')
    fig.update_layout(barmode='group',bargap=.38,yaxis_title=ylabel)
    return chart_style(fig)

def route_chart(s,plan,day):
    points={c.id:(c.x*s.distance_scale,c.y*s.distance_scale) for c in s.customers}
    depot=tuple(x*s.distance_scale for x in s.depot_xy)
    fig=go.Figure()
    for j,r in enumerate(plan.routes):
        if r.day!=day:continue
        coords=[depot]+[points[i] for i in r.stops]+[depot]
        fig.add_scatter(x=[p[0] for p in coords],y=[p[1] for p in coords],mode='lines+markers',name=r.vehicle,line=dict(color=[GREEN,BLUE,'#c3a8f5'][j%3],width=3))
    fig.add_scatter(x=[p[0] for p in points.values()],y=[p[1] for p in points.values()],text=list(points),mode='markers+text',textposition='top center',marker=dict(size=15,color='#aee9f7',line=dict(color='#172f47',width=3)),name='Outlets')
    fig.add_scatter(x=[depot[0]],y=[depot[1]],text=['Depot'],mode='markers+text',textposition='bottom center',marker=dict(size=20,symbol='diamond',color='#ffca9c',line=dict(color='#5b473a',width=3)),name='Depot')
    chart_style(fig,420)
    fig.update_yaxes(scaleanchor='x',scaleratio=1,title=s.distance_unit)
    fig.update_xaxes(title=s.distance_unit)
    return fig


def reduction_chart(monthly,policy,months):
    rows=monthly[monthly.month.isin(months)&monthly.policy.eq(policy)].sort_values('month')
    fig=go.Figure()
    for field,name,color in [('carbon_reduction_pct','Carbon reduction',GREEN),('cost_reduction_pct','Cost reduction',BLUE)]:
        fig.add_bar(y=rows.month,x=rows[field],orientation='h',name=name,marker_color=color,
            text=[f'{v:+.2f}%' if v==v else 'N/A' for v in rows[field]],textposition='outside',cliponaxis=False,
            hovertemplate='%{y}<br>%{x:+.2f}%<extra>%{fullData.name}</extra>')
    chart_style(fig,350)
    fig.update_layout(barmode='group',bargap=.38,margin=dict(l=12,r=65,t=45,b=30))
    fig.update_xaxes(title='Reduction versus baseline (%)',zeroline=True,zerolinecolor='#d2edf577',gridcolor='#afd8ee10',showgrid=True)
    fig.update_yaxes(showgrid=False,autorange='reversed',type='category')
    return fig


def ranking_chart(leaderboard):
    rows=leaderboard.sort_values('Validation RMSE')
    colors=[GREEN if win else BLUE if ml else '#516f89' for win,ml in zip(rows['Overall winner'],rows['Selected ML'])]
    fig=go.Figure(go.Bar(x=rows['Validation RMSE'],y=rows.Method,orientation='h',marker_color=colors,
        text=rows['Validation RMSE'].map(lambda x:f'{x:.3f}'),textposition='outside',cliponaxis=False,
        customdata=rows[['Family','Validation MAE']],hovertemplate='%{y}<br>RMSE %{x:.4f}<br>MAE %{customdata[1]:.4f}<br>%{customdata[0]}<extra></extra>'))
    chart_style(fig,440)
    fig.update_layout(margin=dict(l=10,r=55,t=15,b=35),showlegend=False)
    fig.update_yaxes(autorange='reversed',showgrid=False)
    fig.update_xaxes(title='Validation RMSE · product units',showgrid=True,gridcolor='#afd8ee10',range=[0,rows['Validation RMSE'].max()*1.16])
    return fig
