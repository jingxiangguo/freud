// Copyright (c) 2010-2016 The Regents of the University of Michigan
// This file is part of the Freud project, released under the BSD 3-Clause License.

#include <algorithm>
#include <stdexcept>
#include <complex>
#include <utility>
#include <vector>
#include <tbb/tbb.h>
#include <boost/math/special_functions/spherical_harmonic.hpp>

#include "NearestNeighbors.h"
#include "ScopedGILRelease.h"
#include "HOOMDMatrix.h"

using namespace std;
using namespace tbb;

/*! \file NearestNeighbors.h
  \brief Compute the hexatic order parameter for each particle
*/

namespace freud { namespace locality {

// stop using
NearestNeighbors::NearestNeighbors():
    m_box(box::Box()), m_rmax(0), m_num_neighbors(0), m_scale(0), m_strict_cut(false), m_num_points(0), m_num_ref(0),
    m_deficits()
    {
    m_lc = new locality::LinkCell();
    m_deficits = 0;
    }

NearestNeighbors::NearestNeighbors(float rmax,
                                   unsigned int num_neighbors,
                                   float scale,
                                   bool strict_cut):
    m_box(box::Box()), m_rmax(rmax), m_num_neighbors(num_neighbors), m_scale(scale), m_strict_cut(strict_cut), m_num_points(0),
    m_num_ref(0), m_deficits()
    {
    m_lc = new locality::LinkCell(m_box, m_rmax);
    m_deficits = 0;
    }

NearestNeighbors::~NearestNeighbors()
    {
    delete m_lc;
    }

//! Utility function to sort a pair<float, unsigned int> on the first
//! element of the pair
bool compareRsqVectors(const pair<float, pair<unsigned int, vec3<float> > > &left,
                       const pair<float, pair<unsigned int, vec3<float> > > &right)
    {
    return left.first < right.first;
    }

void NearestNeighbors::setCutMode(const bool strict_cut)
    {
    m_strict_cut = strict_cut;
    }

void NearestNeighbors::compute(const box::Box& box,
                               const vec3<float> *ref_pos,
                               unsigned int num_ref,
                               const vec3<float> *pos,
                               unsigned int num_points)
    {
    m_box = box;
    // reallocate the output array if it is not the right size
    if (num_ref != m_num_ref)
        {
        m_rsq_array = std::shared_ptr<float>(new float[num_ref * m_num_neighbors], std::default_delete<float[]>());
        m_neighbor_array = std::shared_ptr<unsigned int>(new unsigned int[num_ref * m_num_neighbors], std::default_delete<unsigned int[]>());
        m_wvec_array = std::shared_ptr<vec3<float> >(new vec3<float> [num_ref * m_num_neighbors], std::default_delete<vec3<float> []>());
        }
    // fill with padded values; rsq set to -1, neighbors set to UINT_MAX
    std::fill(m_rsq_array.get(), m_rsq_array.get()+int(num_ref*m_num_neighbors), -1);
    std::fill(m_neighbor_array.get(), m_neighbor_array.get()+int(num_ref*m_num_neighbors), UINT_MAX);
    for (unsigned int i=0; i<(num_ref*m_num_neighbors); i++)
        {
        m_wvec_array.get()[i] = vec3<float>(-1,-1,-1);
        }
    // will be set to true for the last loop if we are recomputing
    // with the maximum possible cutoff radius
    bool force_last_recompute(false);
    // find the nearest neighbors
    do
        {
        // compute the cell list
        m_lc->computeCellList(m_box, pos, num_points);

        m_deficits = 0;
        parallel_for(blocked_range<size_t>(0,num_ref),
            [=] (const blocked_range<size_t>& r)
            {
            float rmaxsq = m_rmax * m_rmax;
            // tuple<> is c++11, so for now just make a pair with pairs inside
            // this data structure holds rsq, idx
            // vector< pair<float, unsigned int> > neighbors;
            vector< pair<float, pair<unsigned int, vec3<float> > > > neighbors;
            Index2D b_i = Index2D(m_num_neighbors, num_ref);
            for(size_t i=r.begin(); i!=r.end(); ++i)
                {
                // If we have found an incomplete set of neighbors, end now and rebuild
                if(!force_last_recompute && (m_deficits > 0) && !(m_strict_cut))
                    break;
                neighbors.clear();

                //get cell point is in
                vec3<float> posi = ref_pos[i];
                unsigned int ref_cell = m_lc->getCell(posi);
                unsigned int num_adjacent = 0;

                //loop over neighboring cells
                const std::vector<unsigned int>& neigh_cells = m_lc->getCellNeighbors(ref_cell);
                for (unsigned int neigh_idx = 0; neigh_idx < neigh_cells.size(); neigh_idx++)
                    {
                    unsigned int neigh_cell = neigh_cells[neigh_idx];

                    //iterate over particles in cell
                    locality::LinkCell::iteratorcell it = m_lc->itercell(neigh_cell);
                    for (unsigned int j = it.next(); !it.atEnd(); j = it.next())
                        {

                        //compute r between the two particles
                        vec3<float>rij = m_box.wrap(pos[j] - posi);
                        const float rsq = dot(rij, rij);

                        // adds all neighbors within rsq to list of possible neighbors
                        if ((rsq < rmaxsq) && (i != j))
                            {
                            pair<float, pair<unsigned int, vec3<float> > > l_neighbor;
                            l_neighbor.first = rsq;
                            l_neighbor.second = pair<unsigned int, vec3<float> > (j, rij);
                            neighbors.push_back(l_neighbor);
                            num_adjacent++;
                            }
                        }
                    }

                // Add to the deficit count if necessary
                if(!force_last_recompute && (num_adjacent < m_num_neighbors) && !(m_strict_cut))
                    m_deficits += (m_num_neighbors - num_adjacent);
                else
                    {
                    // sort based on rsq
                    sort(neighbors.begin(), neighbors.end(), compareRsqVectors);
                    unsigned int k_max = (neighbors.size() < m_num_neighbors) ? neighbors.size() : m_num_neighbors;
                    for (unsigned int k = 0; k < k_max; k++)
                        {
                        // put the idx into the neighbor array
                        m_rsq_array.get()[b_i(k, i)] = neighbors[k].first;
                        m_neighbor_array.get()[b_i(k, i)] = (neighbors[k].second).first;
                        m_wvec_array.get()[b_i(k, i)] = (neighbors[k].second).second;
                        }
                    }
                }
            });

        // Increase m_rmax
        if(!force_last_recompute && (m_deficits > 0) && !(m_strict_cut))
            {
            m_rmax *= m_scale;
            // check if new r_max would be too large for the cell width
            vec3<float> L = m_box.getNearestPlaneDistance();
            bool too_wide =  m_rmax > L.x/2.0 || m_rmax > L.y/2.0;
            if (!m_box.is2D())
                {
                too_wide |=  m_rmax > L.z/2.0;
                }
            if (too_wide)
                {
                // throw runtime_warning("r_max has become too large to create a viable cell.");
                // for now print
                printf("r_max has become too large to create a viable cell. Returning neighbors found\n");
                m_rmax = min(0.4999f*L.x, 0.4999f*L.y);
                if(!m_box.is2D())
                    m_rmax = min(m_rmax, 0.4999f*L.z);
                force_last_recompute = true;
                }
            m_lc->setCellWidth(m_rmax);
            }
        else if(force_last_recompute)
            // exit the while loop even if there are deficits
            break;
        } while((m_deficits > 0) && !(m_strict_cut));
    // save the last computed number of particles
    m_num_ref = num_ref;
    m_num_points = num_points;
    }

}; }; // end namespace freud::locality
